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
    
    def _build_tools_context(self) -> str:
        """
        Build a context string describing all available tools.
        
        Returns:
            Formatted string with tool names, descriptions, and parameters
        """
        context_parts = ["## Available Tools\n"]
        
        # Add direct movement tools if gateway is available
        if self.gateway:
            context_parts.append("\n### move_to")
            context_parts.append("Move the robot to a target head pose and/or antennas position using a specified interpolation method.")
            context_parts.append("\n**Parameters:**")
            context_parts.append("- `duration` (float): Duration of movement in seconds (default: 1.0)")
            context_parts.append("- `method` (string): Interpolation method - 'linear', 'minjerk', 'ease', or 'cartoon' (default: 'cartoon')")
            context_parts.append("- `roll` (float): Roll angle in degrees (default: 0.0)")
            context_parts.append("- `pitch` (float): Pitch angle in degrees (default: 0.0)")
            context_parts.append("- `yaw` (float): Yaw angle in degrees (default: 0.0)")
            context_parts.append("- `antennas` (list): List of two antenna angles in degrees [left, right] (default: [0.0, 0.0])")
            context_parts.append("- `body_yaw` (float): Body yaw angle in degrees (default: 0.0)")
            
            context_parts.append("\n### move_smoothly_to")
            context_parts.append("Move the robot smoothly using sinusoidal interpolation to a target pose.")
            context_parts.append("\n**Parameters:**")
            context_parts.append("- `duration` (float): Duration of movement in seconds (default: 1.0)")
            context_parts.append("- `roll` (float): Roll angle in degrees (default: 0.0)")
            context_parts.append("- `pitch` (float): Pitch angle in degrees (default: 0.0)")
            context_parts.append("- `yaw` (float): Yaw angle in degrees (default: 0.0)")
            context_parts.append("- `antennas` (list): List of two antenna angles in degrees [left, right] (default: [0.0, 0.0])")
            context_parts.append("- `body_yaw` (float): Body yaw angle in degrees (default: 0.0)")
            
            context_parts.append("\n### move_cyclically")
            context_parts.append("Move the robot in a cyclical pattern (smooth movement there and back).")
            context_parts.append("\n**Parameters:**")
            context_parts.append("- `duration` (float): Total duration of cyclical movement in seconds (default: 1.0)")
            context_parts.append("- `repetitions` (int): Number of repetitions (default: 1)")
            context_parts.append("- `roll` (float): Roll angle in degrees (default: 0.0)")
            context_parts.append("- `pitch` (float): Pitch angle in degrees (default: 0.0)")
            context_parts.append("- `yaw` (float): Yaw angle in degrees (default: 0.0)")
            context_parts.append("- `antennas` (list): List of two antenna angles in degrees [left, right] (default: [0.0, 0.0])")
            context_parts.append("- `body_yaw` (float): Body yaw angle in degrees (default: 0.0)")
        
        for tool in self.tools_definitions:
            name = tool.get("name", "unknown")
            description = tool.get("description", "No description")
            parameters = tool.get("parameters", {})
            
            context_parts.append(f"\n### {name}")
            context_parts.append(f"{description}")
            
            # Add required parameters
            required = parameters.get("required", [])
            if required:
                context_parts.append("\n**Required parameters:**")
                for param in required:
                    param_name = param.get("name")
                    param_type = param.get("type")
                    param_desc = param.get("description", "")
                    context_parts.append(f"- `{param_name}` ({param_type}): {param_desc}")
            
            # Add optional parameters
            optional = parameters.get("optional", [])
            if optional:
                context_parts.append("\n**Optional parameters:**")
                for param in optional:
                    param_name = param.get("name")
                    param_type = param.get("type")
                    param_default = param.get("default")
                    param_desc = param.get("description", "")
                    default_str = f" (default: {param_default})" if param_default is not None else ""
                    context_parts.append(f"- `{param_name}` ({param_type}){default_str}: {param_desc}")
        
        return "\n".join(context_parts)
    
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
        # Build the context with available tools
        #tools_context = self._build_tools_context()
        
        # Create the user message
        user_message = f"Action: {action_string}"
        
        # Build messages for LLM
        messages = [
            {"role": "system", "content": self.system_prompt},
            {"role": "user", "content": user_message}
        ]
        
        logger.debug(f"Sending action to LLM for parsing: {action_string}")
        
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
                    return parsed
                else:
                    logger.error(f"No valid JSON found in LLM response: {content}")
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
        
        logger.info(f"🎯 Processing action: {action_string}")
        
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
                    try:
                        if tool_name == "move_to":
                            await asyncio.to_thread(self.gateway.move_to, **parameters)
                        elif tool_name == "move_smoothly_to":
                            await asyncio.to_thread(self.gateway.move_smoothly_to, **parameters)
                        elif tool_name == "move_cyclically":
                            await asyncio.to_thread(self.gateway.move_cyclically, **parameters)
                    except Exception as e:
                        logger.error(f"Error executing {tool_name}: {e}")
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
                await self.actions_queue.enqueue_action(action_str)
            
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
