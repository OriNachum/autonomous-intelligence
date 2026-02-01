"""Agent loader - loads agents from agents/<name>/ directories."""

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional


@dataclass
class Agent:
    """Loaded agent configuration."""
    name: str
    system_prompt: str
    user_prompt: Optional[str] = None
    wrapper_module: Optional[str] = None
    tools: list[dict] = field(default_factory=list)


def find_agents_dir() -> Path:
    """Find the agents directory relative to project root."""
    # Since this file is in src/qq/agents/__init__.py, the agents directory is this directory
    return Path(__file__).parent


def load_agent(name: str) -> Agent:
    """
    Load an agent by name from the agents directory.
    
    Agent structure:
        agents/<name>/<name>.system.md  - System prompt (required)
        agents/<name>/<name>.user.md    - Optional user prompt template
        agents/<name>/<name>.py         - Optional Python wrapper
    
    Args:
        name: Agent name (directory name in agents/)
        
    Returns:
        Loaded Agent configuration
    """
    agents_dir = find_agents_dir()
    agent_dir = agents_dir / name
    
    # Check for agent directory
    if not agent_dir.exists():
        if name == "default":
            # Create default agent
            return _create_default_agent(agent_dir)
        raise FileNotFoundError(f"Agent '{name}' not found in {agents_dir}")
    
    # Load system prompt (required) - check .system.md first, then .system.md
    system_file = agent_dir / f"{name}.system.md"
    if not system_file.exists():
        system_file = agent_dir / f"{name}.system.md"
    if not system_file.exists():
        # Try any .system.md or .system.md file
        role_files = list(agent_dir.glob("*.system.md"))
        system_files = list(agent_dir.glob("*.system.md"))
        if role_files:
            system_file = role_files[0]
        elif system_files:
            system_file = system_files[0]
        else:
            raise FileNotFoundError(f"No system/role prompt found for agent '{name}'")
    
    system_prompt = system_file.read_text().strip()
    
    # Load optional user prompt
    user_prompt = None
    user_file = agent_dir / f"{name}.user.md"
    if user_file.exists():
        user_prompt = user_file.read_text().strip()
    
    # Check for Python wrapper
    wrapper_module = None
    wrapper_file = agent_dir / f"{name}.py"
    if wrapper_file.exists():
        wrapper_module = str(wrapper_file)
    
    return Agent(
        name=name,
        system_prompt=system_prompt,
        user_prompt=user_prompt,
        wrapper_module=wrapper_module,
    )


def _create_default_agent(agent_dir: Path) -> Agent:
    """Create and return the default agent."""
    agent_dir.mkdir(parents=True, exist_ok=True)
    
    system_prompt = """You are a helpful AI assistant.

You are friendly, knowledgeable, and concise. You help users with their questions and tasks.

When using tools, explain what you're doing and share the results clearly.

Keep responses focused and actionable. Use markdown formatting when it improves readability."""
    
    system_file = agent_dir / "default.system.md"
    system_file.write_text(system_prompt)
    
    return Agent(
        name="default",
        system_prompt=system_prompt,
    )


def list_agents() -> list[str]:
    """List available agent names."""
    agents_dir = find_agents_dir()
    
    agents = []
    for item in agents_dir.iterdir():
        if item.is_dir() and not item.name.startswith("."):
            # Check if it has a system prompt
            if list(item.glob("*.system.md")):
                agents.append(item.name)
    
    return sorted(agents)
