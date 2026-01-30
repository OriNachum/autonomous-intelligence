"""MCP tool loader - loads tools from mcp.json configuration."""

import json
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Optional


@dataclass
class MCPTool:
    """An MCP tool definition."""
    name: str
    description: str
    parameters: dict
    server_name: str
    

@dataclass 
class MCPServer:
    """An MCP server configuration."""
    name: str
    command: str
    transport: str = "stdio"
    env: dict = field(default_factory=dict)
    process: Optional[subprocess.Popen] = None
    

class MCPLoader:
    """
    Loads and manages MCP servers and their tools.
    
    Parses mcp.json and connects to configured servers.
    """
    
    def __init__(self, config_path: Optional[Path] = None):
        self.config_path = config_path or self._find_config()
        self.servers: dict[str, MCPServer] = {}
        self.tools: list[MCPTool] = []
        self._tool_handlers: dict[str, Callable] = {}
    
    def _find_config(self) -> Path:
        """Find mcp.json configuration file."""
        # Try relative to package
        package_dir = Path(__file__).parent.parent.parent
        config = package_dir / "mcp.json"
        if config.exists():
            return config
        
        # Try current directory
        cwd_config = Path.cwd() / "mcp.json"
        if cwd_config.exists():
            return cwd_config
        
        return config  # Return default path even if doesn't exist
    
    def load(self) -> list[dict]:
        """
        Load MCP configuration and return tools in OpenAI format.
        
        Returns:
            List of tool definitions in OpenAI function calling format
        """
        if not self.config_path.exists():
            return []
        
        try:
            with open(self.config_path) as f:
                config = json.load(f)
        except (json.JSONDecodeError, IOError):
            return []
        
        servers = config.get("servers", [])
        if not servers:
            return []
        
        # For now, we support a simplified format where tools are defined inline
        # Full MCP protocol support (stdio subprocess) can be added later
        tools_config = config.get("tools", [])
        
        openai_tools = []
        for tool in tools_config:
            openai_tools.append({
                "type": "function",
                "function": {
                    "name": tool["name"],
                    "description": tool.get("description", ""),
                    "parameters": tool.get("parameters", {"type": "object", "properties": {}}),
                }
            })
            
            # Store handler info if provided
            if "handler" in tool:
                self._tool_handlers[tool["name"]] = tool["handler"]
        
        return openai_tools
    
    def execute_tool(self, name: str, args: dict) -> str:
        """
        Execute a tool by name.
        
        Args:
            name: Tool name
            args: Tool arguments
            
        Returns:
            Tool execution result as string
        """
        if name not in self._tool_handlers:
            return f"Tool '{name}' not found or has no handler"
        
        handler = self._tool_handlers[name]
        
        # Handler can be a module path or inline function
        if isinstance(handler, str):
            # Import and call module.function
            try:
                module_path, func_name = handler.rsplit(".", 1)
                import importlib
                module = importlib.import_module(module_path)
                func = getattr(module, func_name)
                result = func(**args)
                return json.dumps(result) if not isinstance(result, str) else result
            except Exception as e:
                return f"Error executing tool: {e}"
        
        return "Handler type not supported"
    
    def get_tool_executor(self) -> Callable[[str, dict], str]:
        """Get a tool executor function for use with VLLMClient."""
        return self.execute_tool


def load_mcp_tools(config_path: Optional[Path] = None) -> tuple[list[dict], Callable]:
    """
    Convenience function to load MCP tools.
    
    Returns:
        Tuple of (tools list, executor function)
    """
    loader = MCPLoader(config_path)
    tools = loader.load()
    return tools, loader.get_tool_executor()
