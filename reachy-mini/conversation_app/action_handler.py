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
from typing import Optional, Dict, Any, List
from pathlib import Path
from .actions_queue import AsyncActionsQueue
from .logger import get_logger

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
                 llm_url: Optional[str] = None):
        """
        Initialize the action handler.
        
        Args:
            gateway: ReachyGateway instance for direct robot control (optional)
            reachy_base_url: URL for reachy-daemon (if None, uses REACHY_BASE_URL env var)
            tools_repository_path: Path to tools_repository directory
            llm_url: URL for LLM chat completions (if None, uses default)
        """
        # Store gateway instance for direct robot control
        self.gateway = gateway
        
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
                reachy_base_url=reachy_base_url,
                tools_repository_path=tools_repository_path
            )
            logger.info("✓ Action handler initialized")
        except Exception as e:
            logger.error(f"❌ Failed to initialize actions queue: {e}")
            raise
    
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
                    except Exception as e:
                        logger.warning(f"Failed to get state before command: {e}")
                
                # Audit log: command started with exact parameters
                audit_logger.log_command_started(tool_name, parameters, state_before)
                
                # Check if this is a direct movement command
                if self.gateway and tool_name in ["move_to", "move_smoothly_to", "move_cyclically"]:
                    logger.info(f"  ⚡ Executing direct movement: {tool_name} with {parameters}")
                    
                    # Map method string to InterpolationTechnique enum if needed
                    if "method" in parameters and isinstance(parameters["method"], str):
                        from reachy_mini.utils.interpolation import InterpolationTechnique
                        method_map = {
                            "linear": InterpolationTechnique.LINEAR,
                            "minjerk": InterpolationTechnique.MIN_JERK,
                            #"ease": InterpolationTechnique.EASE,
                            "cartoon": InterpolationTechnique.CARTOON
                        }
                        parameters["method"] = method_map.get(parameters["method"].lower(), InterpolationTechnique.CARTOON)
                    
                    # Execute movement method in a thread to avoid blocking
                    success = True
                    try:
                        if tool_name == "move_to":
                            await asyncio.to_thread(self.gateway.move_to, **parameters)
                        elif tool_name == "move_smoothly_to":
                            await asyncio.to_thread(self.gateway.move_smoothly_to, **parameters)
                        elif tool_name == "move_cyclically":
                            await asyncio.to_thread(self.gateway.move_cyclically, **parameters)
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
                        except Exception as e:
                            logger.warning(f"Failed to get state after command: {e}")
                    
                    # Audit log: command finished
                    audit_logger.log_command_finished(tool_name, state_after, success=success)
                    continue
                
                # Build action string for actions_queue
                if parameters:
                    # Convert parameters to action string format
                    param_strs = []
                    for key, value in parameters.items():
                        if isinstance(value, str):
                            param_strs.append(f"{key}='{value}'")
                        else:
                            param_strs.append(f"{key}={value}")
                    
                    action_str = f"{tool_name}({', '.join(param_strs)})"
                else:
                    action_str = tool_name
                
                logger.info(f"  ⚡ Executing: {action_str}")
                
                # Execute via actions queue
                success = True
                try:
                    await self.actions_queue.enqueue_action(action_str)
                except Exception as e:
                    logger.error(f"Error executing {action_str}: {e}")
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
                    except Exception as e:
                        logger.warning(f"Failed to get state after command: {e}")
                
                # Audit log: command finished
                audit_logger.log_command_finished(tool_name, state_after, success=success)
            
        except Exception as e:
            logger.error(f"❌ Error executing action: {e}")

    
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
