"""MCP tool loader - loads tools from mcp.json and connects to stdio servers."""

import asyncio
import json
import os
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Optional

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client


@dataclass
class MCPServerConfig:
    """An MCP server configuration from mcp.json."""
    name: str
    command: list[str]
    env: dict[str, str] = field(default_factory=dict)


class MCPLoader:
    """
    Loads and manages MCP servers and their tools.
    
    Parses mcp.json and connects to configured stdio servers.
    """
    
    def __init__(self, config_path: Optional[Path] = None):
        self.config_path = config_path or self._find_config()
        self.servers: dict[str, MCPServerConfig] = {}
        self._tools: list[dict] = []
        self._tool_to_server: dict[str, str] = {}  # tool name -> server name
        self._sessions: dict[str, tuple[ClientSession, Any, Any]] = {}  # server -> (session, read, write)
    
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
    
    def _load_config(self) -> dict:
        """Load mcp.json config file."""
        if not self.config_path.exists():
            return {}
        
        try:
            with open(self.config_path) as f:
                return json.load(f)
        except (json.JSONDecodeError, IOError):
            return {}
    
    def load(self) -> list[dict]:
        """
        Load MCP configuration and connect to servers.
        
        Returns:
            List of tool definitions in OpenAI function calling format
        """
        config = self._load_config()
        servers_config = config.get("mcpServers", config.get("servers", {}))
        
        if not servers_config:
            return []
        
        # Parse server configurations
        for name, server_config in servers_config.items():
            command = server_config.get("command", "")
            args = server_config.get("args", [])
            
            if command:
                full_command = [command] + args
                env = server_config.get("env", {})
                self.servers[name] = MCPServerConfig(
                    name=name,
                    command=full_command,
                    env=env,
                )
        
        # Connect to servers and get tools
        if self.servers:
            self._tools = asyncio.run(self._connect_and_list_tools())
        
        return self._tools
    
    async def _connect_and_list_tools(self) -> list[dict]:
        """Connect to all servers and list their tools."""
        all_tools = []
        
        for name, server in self.servers.items():
            try:
                tools = await self._get_server_tools(name, server)
                all_tools.extend(tools)
            except Exception as e:
                print(f"Warning: Failed to connect to MCP server '{name}': {e}", file=sys.stderr)
        
        return all_tools
    
    async def _get_server_tools(self, name: str, server: MCPServerConfig) -> list[dict]:
        """Get tools from a single server."""
        env = {**os.environ, **server.env}
        
        server_params = StdioServerParameters(
            command=server.command[0],
            args=server.command[1:] if len(server.command) > 1 else [],
            env=env,
        )
        
        async with stdio_client(server_params) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                
                # List tools
                tools_result = await session.list_tools()
                
                openai_tools = []
                for tool in tools_result.tools:
                    self._tool_to_server[tool.name] = name
                    
                    # Convert to OpenAI format
                    openai_tools.append({
                        "type": "function",
                        "function": {
                            "name": tool.name,
                            "description": tool.description or "",
                            "parameters": tool.inputSchema if tool.inputSchema else {
                                "type": "object",
                                "properties": {},
                            },
                        }
                    })
                
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
        if name not in self._tool_to_server:
            return f"Tool '{name}' not found"
        
        server_name = self._tool_to_server[name]
        server = self.servers[server_name]
        
        try:
            result = asyncio.run(self._call_tool(server, name, args))
            return result
        except Exception as e:
            return f"Error executing tool '{name}': {e}"
    
    async def _call_tool(self, server: MCPServerConfig, tool_name: str, args: dict) -> str:
        """Call a tool on a server."""
        env = {**os.environ, **server.env}
        
        server_params = StdioServerParameters(
            command=server.command[0],
            args=server.command[1:] if len(server.command) > 1 else [],
            env=env,
        )
        
        async with stdio_client(server_params) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                
                result = await session.call_tool(tool_name, args)
                
                # Extract text from result
                if result.content:
                    texts = [c.text for c in result.content if hasattr(c, 'text')]
                    return "\n".join(texts)
                
                return ""
    
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
