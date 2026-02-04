"""Agent loader - loads agents from agents/<name>/ directories.

Updated for parallel execution support:
- FileManager uses session-isolated state directories
- Default agent creation is atomic (race-safe)
"""

import os
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional, Tuple

from strands import Agent, tool
from strands.models import OpenAIModel

from qq.session import get_session_dir
from qq.services.file_manager import FileManager


def get_model() -> OpenAIModel:
    """
    Get the configured OpenAI/vLLM model.

    Returns:
        Configured OpenAIModel instance
    """
    start_url = os.getenv("OPENAI_BASE_URL", os.getenv("VLLM_URL", "http://localhost:8000/v1"))
    api_key = os.getenv("OPENAI_API_KEY", "EMPTY")
    model_name = os.getenv("MODEL_NAME", os.getenv("MODEL_ID", "model-name"))

    return OpenAIModel(
        model_id=model_name,
        client_args={
            "base_url": start_url,
            "api_key": api_key,
        }
    )


def find_agents_dir() -> Path:
    """Find the agents directory relative to project root."""
    # Since this file is in src/qq/agents/__init__.py, the agents directory is this directory
    return Path(__file__).parent


def _create_skill_tool(skill, model):
    """
    Wrap a Skill into a Strands Agent and then into a Tool.

    Args:
        skill: Skill object (name, description, content, etc.)
        model: OpenAIModel instance to propergate to sub-agent

    Returns:
        A callable tool function decorated with @tool
    """
    # Create the sub-agent for this skill
    # The skill content becomes the system prompt
    sub_agent = Agent(
        name=skill.name,
        system_prompt=skill.content,
        model=model,
    )

    # Create the wrapper function
    def skill_wrapper(query: str) -> str:
        # We invoke the sub-agent
        try:
            # strands Agent is callable with text
            return sub_agent(query)
        except Exception as e:
            return f"Error executing skill {skill.name}: {e}"

    # Set metadata for the tool
    # The name must be a valid python identifier? Strands likely uses function name.
    safe_name = skill.name.replace("-", "_").replace(" ", "_").lower()
    skill_wrapper.__name__ = f"{safe_name}_assistant"
    # Docstring is crucial for the Orchestrator to know when to use it
    skill_wrapper.__doc__ = f"Specialized assistant for {skill.name}. {skill.description}. Use this tool for queries related to {skill.name}."

    # Decorate
    return tool(skill_wrapper)


def _create_default_agent_safely(agent_dir: Path, system_prompt: str) -> None:
    """Create default agent system file atomically.

    Uses atomic file creation (temp file + hard link) to prevent
    race conditions when multiple instances try to create the default agent.

    Args:
        agent_dir: Directory for the agent
        system_prompt: The system prompt content
    """
    system_file = agent_dir / "default.system.md"

    # Fast path: if file exists, nothing to do
    if system_file.exists():
        return

    agent_dir.mkdir(parents=True, exist_ok=True)

    # Atomic create: write to temp, then link
    fd, tmp_path = tempfile.mkstemp(
        dir=agent_dir,
        suffix=".system.md.tmp"
    )
    try:
        with os.fdopen(fd, 'w') as f:
            f.write(system_prompt)

        # Try to create hard link (atomic on POSIX)
        # If file already exists (another instance created it), this raises FileExistsError
        try:
            os.link(tmp_path, system_file)
        except FileExistsError:
            # Another instance created it first - that's fine
            pass
        except OSError:
            # Hard links might not work (e.g., cross-device)
            # Fall back to rename (still atomic, but overwrites)
            if not system_file.exists():
                os.replace(tmp_path, system_file)
    finally:
        # Clean up temp file
        try:
            os.unlink(tmp_path)
        except OSError:
            pass


def load_agent(name: str) -> Tuple[Agent, FileManager]:
    """
    Load an agent by name from the agents directory.

    Returns:
        Tuple of (Agent, FileManager) - FileManager is needed for history capture
    """
    agents_dir = find_agents_dir()
    agent_dir = agents_dir / name

    # Check for agent directory
    if not agent_dir.exists():
        if name == "default":
            # Create default agent
            return _create_default_agent(agent_dir)
        raise FileNotFoundError(f"Agent '{name}' not found in {agents_dir}")

    # Load system prompt (required)
    system_file = agent_dir / f"{name}.system.md"
    if not system_file.exists():
        # Try any .system.md file
        system_files = list(agent_dir.glob("*.system.md"))
        if system_files:
            system_file = system_files[0]
        else:
            raise FileNotFoundError(f"No system/role prompt found for agent '{name}'")

    system_prompt = system_file.read_text().strip()

    # Configure Model
    model = get_model()

    # Load Skills and convert to Tools
    agent_tools = []
    try:
        from qq.skills import load_all_skills
        skills = load_all_skills()
        for skill in skills:
            t = _create_skill_tool(skill, model)
            agent_tools.append(t)
    except ImportError:
        # If qq.skills not found (setup issue), strictly speaking we should fail or warn
        pass
    except Exception as e:
        # Logging error properly would be better
        print(f"Warning: Failed to load skills as tools: {e}")

    # Initialize FileManager with session-isolated state directory
    base_dir = Path.home() / ".qq"
    session_dir = get_session_dir(base_dir, name)
    file_manager = FileManager(session_dir)

    @tool
    def read_file(path: str) -> str:
        """
        Read the content of a file.

        Args:
            path: Absolute or relative path (relative to current session directory).
        """
        return file_manager.read_file(path)

    @tool
    def list_files(pattern: str = "*", recursive: bool = False, use_regex: bool = False) -> str:
        """
        List files in the current session directory.

        Args:
            pattern: Filter files by glob pattern (default "*") or regex.
            recursive: Whether to search recursively.
            use_regex: If True, pattern is treated as regex.
        """
        return file_manager.list_files(pattern, recursive, use_regex)

    @tool
    def set_directory(path: str) -> str:
        """
        Set the current session directory for file operations.

        Args:
            path: Target directory path (absolute or relative).
        """
        return file_manager.set_directory(path)

    agent_tools.extend([read_file, list_files, set_directory])

    # Instantiate Strands Agent
    agent = Agent(
        name=name,
        system_prompt=system_prompt,
        model=model,
        tools=agent_tools
    )

    return agent, file_manager


def _create_default_agent(agent_dir: Path) -> Tuple[Agent, FileManager]:
    """Create and return the default agent with atomic file creation."""
    system_prompt = """You are a helpful AI assistant.

You are friendly, knowledgeable, and concise. You help users with their questions and tasks.

When using tools, explain what you're doing and share the results clearly.

Keep responses focused and actionable. Use markdown formatting when it improves readability."""

    # Atomic creation of default agent
    _create_default_agent_safely(agent_dir, system_prompt)

    model = get_model()

    # Also load skills for default agent
    agent_tools = []
    try:
        from qq.skills import load_all_skills
        skills = load_all_skills()
        for skill in skills:
            t = _create_skill_tool(skill, model)
            agent_tools.append(t)
    except Exception:
        pass

    # Initialize FileManager with session-isolated state directory
    base_dir = Path.home() / ".qq"
    session_dir = get_session_dir(base_dir, "default")
    file_manager = FileManager(session_dir)

    @tool
    def read_file(path: str) -> str:
        """
        Read the content of a file.

        Args:
            path: Absolute or relative path (relative to current session directory).
        """
        return file_manager.read_file(path)

    @tool
    def list_files(pattern: str = "*", recursive: bool = False, use_regex: bool = False) -> str:
        """
        List files in the current session directory.

        Args:
            pattern: Filter files by glob pattern (default "*") or regex.
            recursive: Whether to search recursively.
            use_regex: If True, pattern is treated as regex.
        """
        return file_manager.list_files(pattern, recursive, use_regex)

    @tool
    def set_directory(path: str) -> str:
        """
        Set the current session directory for file operations.

        Args:
            path: Target directory path (absolute or relative).
        """
        return file_manager.set_directory(path)

    agent_tools.extend([read_file, list_files, set_directory])

    agent = Agent(
        name="default",
        system_prompt=system_prompt,
        model=model,
        tools=agent_tools,
    )

    return agent, file_manager


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
