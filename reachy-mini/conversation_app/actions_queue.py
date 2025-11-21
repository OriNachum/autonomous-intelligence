#!/usr/bin/env python3
"""
Actions Queue Manager for Robot Control

This module provides a background actions queue that:
1. Detects action commands between **...** in responses
2. Parses and executes robot actions via reachy-daemon
3. Manages a background action execution queue
4. Can clear the queue when needed (e.g., when user sends new message)

Actions are loaded dynamically from tools_repository/scripts/ directory.
Each action script should have an async execute() function.

Requirements:
    - reachy-daemon running (default: http://localhost:8000)
"""

import asyncio
import httpx
import json
import math
import os
import importlib.util
import traceback
from pathlib import Path
from queue import Queue, Empty
from typing import Optional, Dict, Any
import threading
import logging

logger = logging.getLogger(__name__)

# Default reachy-daemon URL
DEFAULT_REACHY_BASE_URL = "http://localhost:8000"


class ActionsQueue:
    """Manages robot action execution queue."""
    
    def __init__(self, reachy_base_url: Optional[str] = None, 
                 tools_repository_path: Optional[Path] = None):
        """
        Initialize actions queue.
        
        Args:
            reachy_base_url: URL for reachy-daemon (default: http://localhost:8000)
            tools_repository_path: Path to tools_repository directory
        """
        self.reachy_base_url = reachy_base_url or os.getenv("REACHY_BASE_URL", DEFAULT_REACHY_BASE_URL)
        
        # Default to tools_repository in parent directory
        if tools_repository_path is None:
            tools_repository_path = Path(__file__).parent.parent / "tools_repository"
        self.tools_repository_path = tools_repository_path
        self.scripts_path = tools_repository_path / "scripts"
        
        self.action_queue = Queue()
        self.execution_thread = None
        self.is_executing = False
        self.should_stop = False
        
        # Event loop for async operations in thread
        self.loop = None
        
        # Check if reachy-daemon is available
        self._check_daemon_available()
        
        # Start execution thread
        self._start_execution_thread()
    
    def _check_daemon_available(self):
        """Check if reachy-daemon is available."""
        try:
            import requests
            response = requests.get(f"{self.reachy_base_url}/api/state/full", timeout=2)
            if response.status_code == 200:
                logger.info(f"✓ reachy-daemon available at {self.reachy_base_url}")
            else:
                logger.warning(f"⚠️  reachy-daemon responded with status {response.status_code}")
        except Exception as e:
            logger.warning(f"⚠️  Could not connect to reachy-daemon at {self.reachy_base_url}")
            logger.warning(f"   Error: {e}")
    
    def _start_execution_thread(self):
        """Start the background execution thread."""
        self.execution_thread = threading.Thread(target=self._execution_worker, daemon=True)
        self.execution_thread.start()
    
    def _execution_worker(self):
        """Background worker that processes the action queue."""
        # Create a new event loop for this thread
        self.loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self.loop)
        
        while not self.should_stop:
            try:
                # Get action from queue (blocking with timeout)
                action_data = self.action_queue.get(timeout=0.5)
                
                if action_data is None:  # Poison pill
                    break
                
                # Execute action asynchronously in this thread's event loop
                self.loop.run_until_complete(self._execute_action(action_data))
                
            except Empty:
                continue
            except Exception as e:
                logger.error(f"⚠️  Error in action execution worker: {e}")
                traceback.print_exc()
        
        # Close the event loop
        self.loop.close()
    
    async def _execute_action(self, action_data: Dict[str, Any]):
        """
        Execute a robot action.
        
        Args:
            action_data: Dictionary with 'action' (name) and 'params' (parameters)
        """
        try:
            self.is_executing = True
            action_name = action_data.get('action')
            params = action_data.get('params', {})
            
            logger.info(f"🤖 Executing action: {action_name} with params: {params}")
            
            # Load and execute the action script
            result = await self._load_and_execute_script(action_name, params)
            
            if result.get('status') == 'failed' or 'error' in result:
                logger.error(f"   ❌ Action failed: {result.get('error', 'Unknown error')}")
            else:
                logger.info(f"   ✓ Action completed successfully")
            
        except Exception as e:
            logger.error(f"⚠️  Error executing action '{action_data.get('action')}': {e}")
            traceback.print_exc()
        finally:
            self.is_executing = False
    
    async def _load_and_execute_script(self, action_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
        """
        Load and execute an action script from tools_repository/scripts/.
        
        Args:
            action_name: Name of the action (e.g., 'nod_head', 'look_at_direction')
            params: Parameters to pass to the action
            
        Returns:
            Result dictionary from the action execution
        """
        script_file = self.scripts_path / f"{action_name}.py"
        
        if not script_file.exists():
            logger.error(f"   ❌ Action script not found: {script_file}")
            return {"error": f"Action script not found: {action_name}", "status": "failed"}
        
        try:
            # Load the script module
            spec = importlib.util.spec_from_file_location(action_name, script_file)
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            
            # Check if module has execute function
            if not hasattr(module, 'execute'):
                return {"error": f"Action script missing execute function: {action_name}", "status": "failed"}
            
            # Execute the action with helper functions
            result = await module.execute(
                self._make_request,
                self._create_head_pose,
                None,  # tts_queue is handled separately
                params
            )
            
            return result if result else {"status": "success"}
            
        except Exception as e:
            logger.error(f"   ❌ Error loading/executing script: {e}")
            traceback.print_exc()
            return {"error": str(e), "status": "failed"}
    
    def _create_head_pose(
        self,
        x: float = 0.0,
        y: float = 0.0,
        z: float = 0.0,
        roll: float = 0.0,
        pitch: float = 0.0,
        yaw: float = 0.0,
        degrees: bool = False,
        mm: bool = False
    ) -> Dict[str, Any]:
        """
        Create a head pose configuration for Reachy Mini.
        
        Args:
            x, y, z: Position offsets (meters by default, mm if mm=True)
            roll, pitch, yaw: Rotation angles (radians by default, degrees if degrees=True)
            degrees: If True, angles are in degrees
            mm: If True, positions are in millimeters
        
        Returns:
            Dictionary with head pose configuration
        """
        if mm:
            x, y, z = x / 1000, y / 1000, z / 1000
        
        if degrees:
            roll = math.radians(roll)
            pitch = math.radians(pitch)
            yaw = math.radians(yaw)
        
        return {
            "x": x,
            "y": y,
            "z": z,
            "roll": roll,
            "pitch": pitch,
            "yaw": yaw
        }
    
    async def _make_request(
        self,
        method: str,
        endpoint: str,
        json_data: Optional[Dict] = None,
        params: Optional[Dict] = None
    ) -> Dict[str, Any]:
        """Make an HTTP request to the Reachy Mini daemon."""
        url = f"{self.reachy_base_url}{endpoint}"
        
        async with httpx.AsyncClient(timeout=30.0) as client:
            try:
                if method.upper() == "GET":
                    response = await client.get(url, params=params)
                elif method.upper() == "POST":
                    response = await client.post(url, json=json_data)
                elif method.upper() == "PUT":
                    response = await client.put(url, json=json_data)
                elif method.upper() == "DELETE":
                    response = await client.delete(url)
                else:
                    raise ValueError(f"Unsupported HTTP method: {method}")
                
                response.raise_for_status()
                return response.json() if response.content else {"status": "success"}
                
            except httpx.HTTPError as e:
                return {"error": str(e), "status": "failed"}
    
    def parse_action_string(self, action_string: str) -> Dict[str, Any]:
        """
        Parse an action string into action name and parameters.
        
        Formats supported:
        - Simple: "nod_head"
        - With params: "look_at_direction(direction=left)"
        - JSON params: "move_head(x=10, y=5, z=0, duration=2.0)"
        
        Args:
            action_string: The action string to parse
            
        Returns:
            Dictionary with 'action' (name) and 'params' (dict)
        """
        action_string = action_string.strip()
        
        # Check if there are parameters
        if '(' in action_string and action_string.endswith(')'):
            # Extract action name and params string
            action_name = action_string[:action_string.index('(')].strip()
            params_str = action_string[action_string.index('(')+1:-1].strip()
            
            # Parse parameters
            params = {}
            if params_str:
                # Split by comma, but respect nested parentheses
                param_pairs = []
                current = ""
                depth = 0
                for char in params_str:
                    if char == ',' and depth == 0:
                        param_pairs.append(current.strip())
                        current = ""
                    else:
                        if char in '([{':
                            depth += 1
                        elif char in ')]}':
                            depth -= 1
                        current += char
                if current.strip():
                    param_pairs.append(current.strip())
                
                # Parse each param pair
                for pair in param_pairs:
                    if '=' in pair:
                        key, value = pair.split('=', 1)
                        key = key.strip()
                        value = value.strip()
                        
                        # Try to parse value as JSON types
                        try:
                            # Try to evaluate as Python literal
                            import ast
                            params[key] = ast.literal_eval(value)
                        except:
                            # Keep as string if parsing fails
                            params[key] = value
            
            return {"action": action_name, "params": params}
        else:
            # Simple action name without parameters
            return {"action": action_string, "params": {}}
    
    def enqueue_action(self, action_string: str):
        """
        Parse and enqueue an action for execution.
        
        Args:
            action_string: Action string (e.g., "nod_head" or "look_at_direction(direction=left)")
        """
        try:
            action_data = self.parse_action_string(action_string)
            logger.info(f"⚙️  Enqueueing action: {action_data['action']}")
            self.action_queue.put(action_data)
        except Exception as e:
            logger.error(f"⚠️  Error parsing action string '{action_string}': {e}")
    
    def clear_queue(self):
        """Clear all pending actions from the queue."""
        # Clear the queue
        cleared_count = 0
        while not self.action_queue.empty():
            try:
                self.action_queue.get_nowait()
                cleared_count += 1
            except Empty:
                break
        
        if cleared_count > 0:
            logger.info(f"🚫 Actions queue cleared ({cleared_count} actions removed)")
    
    def cleanup(self):
        """Clean up resources."""
        # Stop execution thread
        self.should_stop = True
        self.action_queue.put(None)  # Poison pill
        
        # Clear any remaining actions
        self.clear_queue()
        
        # Wait for thread to finish
        if self.execution_thread and self.execution_thread.is_alive():
            self.execution_thread.join(timeout=2.0)
        
        logger.info("🧹 Actions queue cleanup complete")


# Async wrapper for use in async applications
class AsyncActionsQueue:
    """Async wrapper for ActionsQueue."""
    
    def __init__(self, reachy_base_url: Optional[str] = None,
                 tools_repository_path: Optional[Path] = None):
        """
        Initialize async actions queue.
        
        Args:
            reachy_base_url: URL for reachy-daemon
            tools_repository_path: Path to tools_repository directory
        """
        self.actions_queue = ActionsQueue(reachy_base_url, tools_repository_path)
    
    async def enqueue_action(self, action_string: str):
        """Enqueue action for execution (async version)."""
        # Run in thread pool to avoid blocking
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(None, self.actions_queue.enqueue_action, action_string)
    
    async def clear_queue(self):
        """Clear the queue (async version)."""
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(None, self.actions_queue.clear_queue)
    
    def cleanup(self):
        """Clean up resources."""
        self.actions_queue.cleanup()


# Test function
async def test_actions():
    """Test the actions queue."""
    logger.setLevel(logging.DEBUG)
    logging.basicConfig(level=logging.DEBUG)
    
    print("=" * 70)
    print("Testing Actions Queue")
    print("=" * 70)
    
    actions = AsyncActionsQueue()
    
    try:
        # Test simple action
        print("\n1. Testing simple action: nod_head")
        await actions.enqueue_action("nod_head")
        await asyncio.sleep(3)
        
        # Test action with parameters
        print("\n2. Testing action with params: look_at_direction(direction=left)")
        await actions.enqueue_action("look_at_direction(direction=left, duration=1.5)")
        await asyncio.sleep(3)
        
        # Test multiple actions
        print("\n3. Testing multiple actions in sequence")
        await actions.enqueue_action("nod_head(duration=1.0, angle=10)")
        await actions.enqueue_action("shake_head(duration=1.0, angle=20)")
        await actions.enqueue_action("reset_head")
        
        # Wait for completion
        print("\nWaiting for actions to complete...")
        await asyncio.sleep(8)
        
        print("\n✓ Test complete")
        
    except Exception as e:
        print(f"\n❌ Error: {e}")
        traceback.print_exc()
    finally:
        actions.cleanup()


if __name__ == "__main__":
    asyncio.run(test_actions())
