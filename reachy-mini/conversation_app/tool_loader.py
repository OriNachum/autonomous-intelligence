#!/usr/bin/env python3
"""
Tool Loader for Conversation App

This module loads tool definitions from the actions directory.
All tool definitions must be in OpenAI function calling format.
"""

import json
import logging
from pathlib import Path
from typing import List, Dict, Any

logger = logging.getLogger(__name__)


def load_tool_definitions(actions_path: Path) -> List[Dict[str, Any]]:
    """
    Load tool definitions from actions directory.
    
    All .json files in the actions directory must be in OpenAI function calling format:
    {
        "type": "function",
        "function": {
            "name": "tool_name",
            "description": "Description of what the tool does",
            "parameters": {
                "type": "object",
                "properties": {
                    "param1": {"type": "string", "description": "..."},
                    "param2": {"type": "number", "description": "..."}
                },
                "required": ["param1"]
            }
        }
    }
    
    Args:
        actions_path: Path to actions directory containing .json definitions
        
    Returns:
        List of tool definitions in OpenAI format
    """
    tools = []
    
    # Load all .json files from actions directory
    # Exclude tools_index.json and any utility files
    exclude_files = {"tools_index.json"}
    
    for tool_file in sorted(actions_path.glob("*.json")):
        if tool_file.name in exclude_files:
            continue
            
        try:
            with open(tool_file, 'r') as f:
                tool_def = json.load(f)
            
            # Validate it's in OpenAI format
            if not validate_openai_format(tool_def):
                logger.warning(f"Skipping {tool_file.name}: Not in OpenAI format")
                continue
            
            tools.append(tool_def)
            logger.debug(f"Loaded tool: {tool_def['function']['name']}")
            
        except Exception as e:
            logger.warning(f"Failed to load tool {tool_file.name}: {e}")
    
    logger.info(f"Loaded {len(tools)} tool definitions")
    return tools


def validate_openai_format(tool_def: Dict[str, Any]) -> bool:
    """
    Validate that a tool definition is in OpenAI format.
    
    Args:
        tool_def: Tool definition to validate
        
    Returns:
        True if valid OpenAI format, False otherwise
    """
    try:
        # Check required top-level fields
        if tool_def.get("type") != "function":
            return False
        
        function = tool_def.get("function", {})
        if not function.get("name"):
            return False
        
        # Parameters are optional but if present must be valid
        if "parameters" in function:
            params = function["parameters"]
            if params.get("type") != "object":
                return False
            # Properties and required are optional
        
        return True
        
    except Exception:
        return False
