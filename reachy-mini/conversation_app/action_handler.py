#!/usr/bin/env python3
"""
Action Handler Module

This module handles robot action execution with LLM-based action parsing:
- Loads action-handler.system.md as system prompt
- Loads all tool definitions from tools_repository
- Uses LLM to parse action strings into proper function calls
- Executes actions through AsyncActionsQueue

The LLM receives the action string from conversation and responds with
properly formatted tool calls that are then executed.
"""

import logging
import os
import json
import httpx
import asyncio
import numpy as np
from typing import Optional, Dict, Any, List
from pathlib import Path
from .actions_queue import AsyncActionsQueue
from .logger import get_logger
from . import mappings

logger = logging.getLogger(__name__)

# Configuration
CHAT_COMPLETIONS_URL = os.environ.get("VLLM_ACTION_URL", "http://localhost:8200/v1/chat/completions")
MODEL_NAME = os.environ.get("MODEL_ID", "RedHatAI/Llama-3.2-3B-Instruct-FP8")


class ActionHandler:
    """Handles robot action execution with LLM-based parsing."""
    
    def __init__(self, 
                 gateway=None,
                 reachy_base_url: Optional[str] = None,
                 tools_repository_path: Optional[Path] = None,
                 llm_url: Optional[str] = None,
                 event_callback: Optional[callable] = None,
                 tts_queue: Optional[Any] = None):
        """
        Initialize the action handler.
        
        Args:
            gateway: ReachyGateway instance for direct robot control (optional)
            reachy_base_url: URL for reachy-daemon (if None, uses REACHY_BASE_URL env var)
            tools_repository_path: Path to tools_repository directory
            llm_url: URL for LLM chat completions (if None, uses default)
            event_callback: Callback function for action execution events
            tts_queue: TTS queue for speech synthesis (for speak action)
        """
        # Store gateway instance for direct robot control
        self.gateway = gateway
        self.event_callback = event_callback
        self.tts_queue = tts_queue
        
        # Get configuration from environment if not provided
        if reachy_base_url is None:
            reachy_base_url = os.environ.get("REACHY_BASE_URL", "http://localhost:8000")
        
        if tools_repository_path is None:
            # Default to tools_repository in parent directory
            tools_repository_path = Path(__file__).parent / "actions"
        
        self.tools_repository_path = tools_repository_path
        self.llm_url = llm_url or CHAT_COMPLETIONS_URL
        
        logger.info(f"Initializing action handler...")
        logger.info(f"  Reachy daemon: {reachy_base_url}")
        logger.info(f"  Tools repository: {tools_repository_path}")
        logger.info(f"  LLM endpoint: {self.llm_url}")
        
        # Load system prompt
        try:
            system_prompt_path = Path(__file__).parent / "agents" / "action-handler" / "action-handler.system.md"
            self.system_prompt = system_prompt_path.read_text()                

            logger.info("✓ Loaded action handler system prompt")
        except Exception as e:
            logger.error(f"❌ Failed to load system prompt: {e}")
            raise
        
#        # Load tool definitions
#        try:
#            self.tools_definitions = self._load_tools_definitions()
#            logger.info(f"✓ Loaded {len(self.tools_definitions)} tool definitions")
#        except Exception as e:
#            logger.error(f"❌ Failed to load tool definitions: {e}")
#            raise
        
        # Initialize actions queue
        try:
            self.actions_queue = AsyncActionsQueue(
                gateway=self.gateway,
                reachy_base_url=reachy_base_url,
                tools_repository_path=tools_repository_path,
                event_callback=self.event_callback,
                tts_queue=self.tts_queue
            )
            logger.info("✓ Action handler initialized")
        except Exception as e:
            logger.error(f"❌ Failed to initialize actions queue: {e}")
            raise
        
        # State tracking for "return" and "back" parameters
        self._initial_state = None  # State at start of command sequence
        self._state_history = []  # Stack of states for "back" functionality
        self._current_doa = None  # Current DOA for "DOA" parameter resolution
    
    def set_doa(self, doa_dict: Optional[Dict[str, float]]):
        """
        Set the current DOA for use with "DOA" parameter.
        
        Args:
            doa_dict: Dictionary with 'angle_degrees' and 'angle_radians' keys, or None
        """
        self._current_doa = doa_dict
        if doa_dict:
            logger.debug(f"DOA set for action handler: {doa_dict['angle_degrees']:.1f}°")
    
    def _resolve_parameter(self, param_name: str, param_value: Any, current_state: Dict[str, Any]) -> Any:
        """
        Resolve special parameter values like 'return', 'back', and 'doa'.
        
        Args:
            param_name: Parameter name ('roll', 'pitch', 'yaw', 'body_yaw', 'antennas', 'duration')
            param_value: Parameter value (could be 'return', 'back', 'doa', or actual value)
            current_state: Current robot state for fallback
        
        Returns:
            Resolved parameter value (numeric or list)
        """
        # If not a string, already resolved
        if not isinstance(param_value, str):
            return param_value
        
        value_lower = param_value.lower().strip()
        
        # Handle "return" - go back to initial state
        if value_lower == 'return':
            if self._initial_state and param_name in self._initial_state:
                resolved = self._initial_state[param_name]
                logger.info(f"  Resolved '{param_name}=return' to {resolved} (initial state)")
                return resolved
            else:
                logger.warning(f"  No initial state for '{param_name}', using current state")
                return current_state.get(param_name)
        
        # Handle "back" - go to previous state in history
        if value_lower == 'back':
            if self._state_history:
                # Get last state from history
                prev_state = self._state_history[-1]
                if param_name in prev_state:
                    resolved = prev_state[param_name]
                    logger.info(f"  Resolved '{param_name}=back' to {resolved} (previous state)")
                    return resolved
            # Fallback to initial state if no history
            if self._initial_state and param_name in self._initial_state:
                resolved = self._initial_state[param_name]
                logger.info(f"  Resolved '{param_name}=back' to {resolved} (no history, using initial)")
                return resolved
            logger.warning(f"  No state history for '{param_name}', using current state")
            return current_state.get(param_name)
        
        # Handle "DOA" - direction of audio
        if value_lower == 'doa':
            if param_name in ['yaw', 'body_yaw']:
                if self._current_doa:
                    # Convert DOA angle to robot yaw
                    # DOA is in compass coordinates, need to convert to robot yaw
                    doa_degrees = self._current_doa['angle_degrees']
                    # Use mappings to convert compass to robot yaw
                    # The DOA is already in the right coordinate system (matches compass)
                    # Robot yaw formula: reachy_yaw = -1 * (compass_angle / 2)
                    robot_yaw = -1.0 * (doa_degrees / 2.0)
                    # Clamp to ±45°
                    robot_yaw = np.clip(robot_yaw, -45.0, 45.0)
                    logger.info(f"  Resolved '{param_name}=DOA' to {robot_yaw:.1f}° (from DOA {doa_degrees:.1f}°)")
                    return robot_yaw
                else:
                    logger.warning(f"  No DOA available for '{param_name}', using current state")
                    return current_state.get(param_name)
            elif param_name == 'antennas':
                # For antennas, use "alert" pose when oriented toward sound
                resolved = mappings.name_to_value('antennas', 'alert')
                logger.info(f"  Resolved 'antennas=DOA' to 'alert' pose: {resolved}")
                return resolved
            else:
                logger.warning(f"  DOA not applicable to '{param_name}', using current state")
                return current_state.get(param_name)
        
        # Not a special value, return as-is
        return param_value
    
    def _load_tools_definitions(self) -> List[Dict[str, Any]]:
        """
        Load all tool definitions from tools_repository.
        
        Returns:
            List of tool definitions with name, description, and parameters
        """
        tools = []
        
        # Load tools index
        tools_index_path = self.tools_repository_path / "tools_index.json"
        if not tools_index_path.exists():
            logger.error(f"Tools index not found: {tools_index_path}")
            return tools
        
        with open(tools_index_path, 'r') as f:
            tools_index = json.load(f)
        
        # Load each enabled tool definition
        for tool_entry in tools_index.get("tools", []):
            if not tool_entry.get("enabled", True):
                continue
            
            definition_file = tool_entry.get("definition_file")
            if not definition_file:
                continue
            
            definition_path = self.tools_repository_path / definition_file
            if not definition_path.exists():
                logger.warning(f"Tool definition not found: {definition_path}")
                continue
            
            try:
                with open(definition_path, 'r') as f:
                    tool_def = json.load(f)
                    tools.append(tool_def)
            except Exception as e:
                logger.warning(f"Failed to load {definition_file}: {e}")
        
        return tools
        
    async def _parse_action_with_llm(self, action_string: str) -> Dict[str, Any]:
        """
        Use LLM to parse action string into structured tool calls.
        
        Args:
            action_string: Raw action string from conversation
            
        Returns:
            Dictionary with parsed action(s) in format:
            {
                "commands": [
                    {"tool_name": "nod_head", "parameters": {"duration": 2.0, "speech": "Yes"}},
                    ...
                ]
            }
        """
        audit_logger = get_logger()
        
        # Build the context with available tools
        #tools_context = self._build_tools_context()
        
        # Create the user message
        user_message = f"Action: {action_string}"
        
        # Inject current state if available
        current_state = None
        if self.gateway:
            try:
                # Get natural language state
                state_natural = self.gateway.get_current_state_natural()
                current_state = state_natural
                state_str = (
                    f"\nCurrent State: "
                    f"looking {state_natural['head_direction']}, "
                    f"{state_natural['head_tilt']}, "
                    f"{state_natural['head_roll']}, "
                    f"antennas {state_natural['antennas']}, "
                    f"body facing {state_natural['body_direction']}"
                )
                user_message += state_str
                logger.debug(f"Injected natural state into prompt: {state_str.strip()}")
            except Exception as e:
                logger.warning(f"Failed to get current state for prompt: {e}")
        
        # Build messages for LLM
        messages = [
            {"role": "system", "content": self.system_prompt},
            {"role": "user", "content": user_message}
        ]
        
        logger.debug(f"Sending action to LLM for parsing: {action_string}")
        
        # Audit log: action LLM request
        audit_logger.log_action_llm_request(user_message, current_state)
        
        try:
            # Make request to LLM
            async with httpx.AsyncClient(timeout=10.0) as client:
                payload = {
                    "model": MODEL_NAME,
                    "messages": messages,
                    "max_tokens": 500,
                    "temperature": 0.1,  # Low temperature for consistent parsing
                    "stream": False
                }
                
                response = await client.post(self.llm_url, json=payload)
                response.raise_for_status()
                
                result = response.json()
                content = result["choices"][0]["message"]["content"]
                
                logger.debug(f"LLM response: {content}")
                
                # Parse JSON response
                # The LLM should respond with JSON starting with {
                # Extract JSON from response
                json_start = content.find('{')
                json_end = content.rfind('}') + 1
                
                if json_start >= 0 and json_end > json_start:
                    json_str = content[json_start:json_end]
                    parsed = json.loads(json_str)
                    
                    # Audit log: action LLM response
                    audit_logger.log_action_llm_response(content, parsed.get("commands", []))
                    
                    return parsed
                else:
                    logger.error(f"No valid JSON found in LLM response: {content}")
                    # Still log the response even if parsing failed
                    audit_logger.log_action_llm_response(content, [])
                    return {"commands": []}
                
        except Exception as e:
            logger.error(f"Error parsing action with LLM: {e}")
            logger.error(f"Action string: {action_string}")
            return {"commands": []}
    
    def _normalize_parameters(self, parameters: Dict[str, Any]) -> Dict[str, Any]:
        """
        Normalize parameters by converting named values to numeric values.
        
        Handles all parameter types:
        - pitch: names like 'up', 'down', 'neutral' -> degrees
        - roll: names like 'left', 'right', 'neutral' -> degrees
        - yaw: compass directions like 'North', 'East' -> degrees
        - body_yaw: compass directions -> degrees
        - antennas: names like 'happy', 'sad', 'neutral' -> [right, left] degrees
        - duration: names like 'fast', 'slow', 'normal' -> seconds
        
        Falls back to numeric values if already provided (backward compatibility).
        
        Args:
            parameters: Original parameters that may contain named or numeric values
            
        Returns:
            Normalized parameters with numeric values
        """
        normalized = {}
        
        for key, value in parameters.items():
            # Skip None values
            if value is None:
                normalized[key] = value
                continue
            
            # Try to convert using mappings module
            try:
                # Special handling for parameters that might need conversion
                if key in ['pitch', 'roll', 'yaw', 'body_yaw', 'antennas', 'duration']:
                    # If already numeric, pass through
                    if isinstance(value, (int, float)):
                        normalized[key] = value
                    elif isinstance(value, list):
                        # Likely antennas already in numeric form
                        normalized[key] = value
                    else:
                        # Try to convert name to value
                        normalized[key] = mappings.name_to_value(key, value)
                        logger.debug(f"Converted {key}='{value}' to {normalized[key]}")
                else:
                    # Pass through other parameters unchanged
                    normalized[key] = value
            except ValueError as e:
                # If conversion fails, try to pass through as-is
                logger.warning(f"Failed to convert parameter {key}='{value}': {e}")
                normalized[key] = value
        
        return normalized
    
    async def execute(self, action_string: str):
        """
        Parse and execute an action using LLM.
        
        Args:
            action_string: Action to execute (natural language or structured)
        """
        if not action_string or not action_string.strip():
            return
        
        audit_logger = get_logger()
        
        logger.info(f"🎯 Processing action: {action_string}")
        
        # Audit log: action received
        audit_logger.log_action_received(action_string)
        
        try:
            # Capture initial state at start of command sequence
            if self.gateway:
                try:
                    raw_state = self.gateway.get_current_state()
                    self._initial_state = {
                        "roll": raw_state[0],
                        "pitch": raw_state[1],
                        "yaw": raw_state[2],
                        "antennas": raw_state[3],
                        "body_yaw": raw_state[4]
                    }
                    # Reset state history for new command sequence
                    self._state_history = []
                    logger.debug(f"Captured initial state: {self._initial_state}")
                except Exception as e:
                    logger.warning(f"Failed to capture initial state: {e}")
                    self._initial_state = None
            
            # Parse action with LLM
            parsed = await self._parse_action_with_llm(action_string)
            
            # Extract commands
            commands = parsed.get("commands", [])
            
            if not commands:
                logger.warning(f"No commands parsed from action: {action_string}")
                return
            logger.info(f"✅ Parsed {len(commands)} command(s) from action")
            # Execute each command
            for cmd in commands:
                tool_name = cmd.get("tool_name")
                parameters = cmd.get("parameters", {})
                
                if not tool_name:
                    logger.warning(f"Command missing tool_name: {cmd}")
                    continue
                
                # Get state before command execution (raw numeric values)
                state_before = None
                if self.gateway:
                    try:
                        # Get raw state in degrees: (roll, pitch, yaw, antennas, body_yaw)
                        raw_state = self.gateway.get_current_state()
                        state_before = {
                            "roll": raw_state[0],
                            "pitch": raw_state[1],
                            "yaw": raw_state[2],
                            "antennas": raw_state[3],
                            "body_yaw": raw_state[4]
                        }
                        
                        # Resolve special parameter values BEFORE normalization
                        resolved_params = {}
                        for key, value in parameters.items():
                            resolved_params[key] = self._resolve_parameter(key, value, state_before)
                        parameters = resolved_params
                        
                    except Exception as e:
                        logger.warning(f"Failed to get state before command: {e}")
                
                # Normalize parameters (convert compass strings to degrees)
                normalized_params = self._normalize_parameters(parameters)
                
                # Audit log: command started with exact numeric parameters
                audit_logger.log_command_started(tool_name, normalized_params, state_before)
                
                # Check if this is a direct movement command
                if self.gateway and tool_name in ["move_smoothly_to"]:
                    logger.info(f"  ⚡ Executing direct movement: {tool_name} with {parameters}")
                                        
                    # Execute movement method in a thread to avoid blocking
                    success = True
                    try:
                        await asyncio.to_thread(self.gateway.move_smoothly_to, **normalized_params)
                    except Exception as e:
                        logger.error(f"Error executing {tool_name}: {e}")
                        success = False
                    
                    # Get state after command execution (raw numeric values)
                    state_after = None
                    if self.gateway:
                        try:
                            # Get raw state in degrees: (roll, pitch, yaw, antennas, body_yaw)
                            raw_state = self.gateway.get_current_state()
                            state_after = {
                                "roll": raw_state[0],
                                "pitch": raw_state[1],
                                "yaw": raw_state[2],
                                "antennas": raw_state[3],
                                "body_yaw": raw_state[4]
                            }
                            
                            # Push state_before to history for "back" functionality
                            # We push the state BEFORE the move, so "back" returns to it
                            if state_before:
                                self._state_history.append(state_before)
                                logger.debug(f"Pushed state to history (depth: {len(self._state_history)})")
                            
                        except Exception as e:
                            logger.warning(f"Failed to get state after command: {e}")
                    
                    # Audit log: command finished
                    audit_logger.log_command_finished(tool_name, state_after, success=success)
                    continue
                
                # Execute via actions queue with structured parameters
                logger.info(f"  ⚡ Executing: {tool_name} with params: {normalized_params}")
                
                success = True
                try:
                    await self.actions_queue.enqueue_command(tool_name, normalized_params)
                except Exception as e:
                    logger.error(f"Error executing {tool_name}: {e}")
                    success = False
                
                # Get state after command execution (raw numeric values)
                state_after = None
                if self.gateway:
                    try:
                        # Get raw state in degrees: (roll, pitch, yaw, antennas, body_yaw)
                        raw_state = self.gateway.get_current_state()
                        state_after = {
                            "roll": raw_state[0],
                            "pitch": raw_state[1],
                            "yaw": raw_state[2],
                            "antennas": raw_state[3],
                            "body_yaw": raw_state[4]
                        }
                        
                        # Push state_before to history for "back" functionality
                        if state_before:
                            self._state_history.append(state_before)
                            logger.debug(f"Pushed state to history (depth: {len(self._state_history)})")
                        
                    except Exception as e:
                        logger.warning(f"Failed to get state after command: {e}")
                
                # Audit log: command finished
                audit_logger.log_command_finished(tool_name, state_after, success=success)
            
        except Exception as e:
            logger.error(f"❌ Error executing tool: {e}")

    
    async def execute_tool(self, tool_name: str, parameters: Dict[str, Any]) -> Dict[str, Any]:
        """
        Execute a tool with structured parameters (bypasses LLM parsing).
        
        This is called directly from the front model's function calling output.
        
        Args:
            tool_name: Name of the tool/action to execute
            parameters: Dictionary of parameters for the tool
            
        Returns:
            Dictionary with execution result and status
        """
        if not tool_name:
            logger.warning("execute_tool called with empty tool_name")
            return {"status": "error", "error": "Empty tool_name"}
        
        audit_logger = get_logger()
        logger.info(f"🎯 Processing tool call: {tool_name}({parameters})")
        
        # Execute via actions queue directly with structured parameters
        try:
            await self.actions_queue.enqueue_command(tool_name, parameters)
            return {
                "status": "success",
                "tool_name": tool_name,
                "parameters": parameters
            }
        except Exception as e:
            logger.error(f"Error executing {tool_name}: {e}")
            return {
                "status": "error",
                "error": str(e),
                "tool_name": tool_name,
                "parameters": parameters
            }





    
    async def clear(self):
        """Clear all pending actions from the queue."""
        logger.debug("Clearing actions queue")
        try:
            await self.actions_queue.clear_queue()
        except Exception as e:
            logger.error(f"❌ Error clearing actions queue: {e}")
    
    def cleanup(self):
        """Clean up resources."""
        logger.debug("Cleaning up action handler")
        try:
            self.actions_queue.cleanup()
        except Exception as e:
            logger.error(f"❌ Error during action handler cleanup: {e}")
