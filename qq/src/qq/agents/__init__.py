"""Agent loader - loads agents from agents/<name>/ directories.

Updated for parallel execution support:
- FileManager uses session-isolated state directories
- Default agent creation is atomic (race-safe)
- ChildProcess enables recursive agent invocation
"""

import json
import os
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional, Tuple, List

from strands import Agent, tool
from strands.models import OpenAIModel

from qq.session import get_session_dir
from qq.services.file_manager import FileManager
from qq.services.child_process import ChildProcess
from qq.services.task_queue import QueueFullError
from qq.services.summarizer import summarize_if_needed
from qq.services.output_guard import guard_output
from qq.services.memory_tools import create_memory_tools


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


def _create_common_tools(file_manager: FileManager, child_process: ChildProcess) -> List:
    """Create common tools shared by all agents.

    Args:
        file_manager: FileManager instance for file operations.
        child_process: ChildProcess instance for recursive agent calls.

    Returns:
        List of tool-decorated functions.
    """
    # File operation tools
    @tool
    def read_file(path: str, start_line: int = 1, num_lines: int = 100) -> str:
        """
        Read the content of a file.

        Args:
            path: Absolute or relative path (relative to current session directory).
            start_line: Line number to start reading from (1-indexed). Default 1.
            num_lines: Number of lines to read. Default 100, max 100.
        """
        return file_manager.read_file(path, start_line, num_lines)

    @tool
    def list_files(
        pattern: str = "*",
        recursive: bool = False,
        use_regex: bool = False,
        offset: int = 0,
        limit: int = 0,
    ) -> str:
        """
        List files in the current session directory with pagination.

        Args:
            pattern: Filter files by glob pattern (default "*") or regex.
            recursive: Whether to search recursively.
            use_regex: If True, pattern is treated as regex.
            offset: Skip first N files (for pagination). Default 0.
            limit: Max files to return. 0 = auto (warns if >20, suggests pagination).

        Returns:
            File listing with metadata, or warning with options if too many files.
        """
        result = file_manager.list_files(pattern, recursive, use_regex, offset, limit)
        return guard_output(result, "list_files")

    @tool
    def set_directory(path: str) -> str:
        """
        Set the current session directory for file operations.

        Args:
            path: Target directory path (absolute or relative).
        """
        return file_manager.set_directory(path)

    @tool
    def count_files(
        path: str = ".",
        pattern: str = "*",
        recursive: bool = False,
        use_regex: bool = False,
    ) -> str:
        """
        Count files in a directory with breakdown by extension.

        Use this to quickly assess folder contents before processing.
        Helpful for planning batch operations or understanding project structure.

        Args:
            path: Directory to count files in (default: current directory).
            pattern: Filter by glob pattern (default "*") or regex.
            recursive: If True, count files in subdirectories too.
            use_regex: If True, treat pattern as regex instead of glob.

        Returns:
            Summary with total count and breakdown by file extension.
        """
        return file_manager.count_files(path, pattern, recursive, use_regex)

    # Child process tools for recursive agent invocation
    @tool
    def delegate_task(task: str, agent: str = "default", context: str = "") -> str:
        """
        Delegate a task to a child QQ agent.

        Use this to break down complex tasks or leverage specialized agents.
        The child agent runs in isolation with its own session and ephemeral notes.

        When to use:
        - Complex tasks that benefit from focused attention
        - Tasks requiring a specialized agent (coder, researcher)
        - Subtasks that can be handled independently

        Args:
            task: The task description or prompt for the child agent.
            agent: Which agent to use (default, coder, etc.).
            context: Initial context to seed the child's working memory.
                     This helps anchor the child to its specific subtask.

        Returns:
            The child agent's response (summarized if large).
        """
        result = child_process.spawn_agent(
            task=task,
            agent=agent,
            initial_context=context if context else None,
        )
        if result.success:
            # Summarize large outputs to prevent token overflow
            return summarize_if_needed(result.output, task)
        else:
            return f"Child agent error: {result.error}"

    @tool
    def run_parallel_tasks(tasks_json: str) -> str:
        """
        Run multiple tasks in parallel using child QQ agents.

        Use this for batch operations where tasks don't depend on each other.

        Args:
            tasks_json: JSON array of task objects, each with:
                - task: The task description (required)
                - agent: Agent to use (optional, default: "default")
                - context: Initial context for child's working memory (optional)

        Example:
            tasks_json = '[
                {"task": "Summarize file A", "context": "Focus on API endpoints"},
                {"task": "Analyze file B", "agent": "coder", "context": "Check for bugs"}
            ]'

        Returns:
            JSON array of results with task, agent, success, output (summarized), and error fields.
        """
        try:
            tasks = json.loads(tasks_json)
            if not isinstance(tasks, list):
                return "Error: tasks_json must be a JSON array"

            results = child_process.run_parallel(tasks)
            return json.dumps([
                {
                    "task": r.task,
                    "agent": r.agent,
                    "success": r.success,
                    # Summarize each child's output to prevent token overflow
                    "output": summarize_if_needed(r.output, r.task) if r.success else r.output,
                    "error": r.error,
                }
                for r in results
            ], indent=2)
        except json.JSONDecodeError as e:
            return f"Invalid JSON: {e}"

    # Queue-based task scheduling tools
    @tool
    def schedule_tasks(tasks_json: str) -> str:
        """
        Schedule multiple tasks for batch execution.

        This queues tasks without immediately executing them, allowing you to
        build up a batch of work before running it all at once. Use this when
        you have many tasks to process and want efficient scheduling.

        Tasks are executed in priority order when execute_scheduled_tasks() is called.

        Args:
            tasks_json: JSON array of task objects, each with:
                - task: The task description (required)
                - agent: Agent to use (optional, default: "default")
                - priority: Higher numbers execute first (optional, default: 0)
                - context: Initial context for child's working memory (optional)

        Example:
            schedule_tasks('[
                {"task": "Process files 1-10", "priority": 2, "context": "Batch 1 of 10"},
                {"task": "Process files 11-20", "priority": 1, "context": "Batch 2 of 10"},
                {"task": "Process files 21-30", "context": "Batch 3 of 10"}
            ]')

        Returns:
            JSON object with queued count, task_ids, and pending count.
        """
        try:
            tasks = json.loads(tasks_json)
            if not isinstance(tasks, list):
                return json.dumps({"error": "tasks_json must be a JSON array"})

            task_ids = child_process.queue_batch(tasks)
            return json.dumps({
                "queued": len(task_ids),
                "task_ids": task_ids,
                "pending": child_process.task_queue.pending_count(),
                "message": f"Queued {len(task_ids)} tasks. Call execute_scheduled_tasks() to run them."
            })
        except QueueFullError as e:
            return json.dumps({"error": str(e)})
        except json.JSONDecodeError as e:
            return json.dumps({"error": f"Invalid JSON: {e}"})

    @tool
    def execute_scheduled_tasks() -> str:
        """
        Execute all scheduled tasks and return results.

        This runs all tasks that were queued via schedule_tasks() and blocks
        until all complete. Tasks are executed in priority order (higher first)
        with up to max_parallel concurrent executions.

        Returns:
            JSON array of results with task, agent, success, output (summarized), and error fields.
        """
        try:
            results = child_process.execute_queue()
            if not results:
                return json.dumps({"message": "No tasks in queue to execute"})

            return json.dumps([
                {
                    "task": r.task,
                    "agent": r.agent,
                    "success": r.success,
                    "output": summarize_if_needed(r.output, r.task) if r.success else r.output,
                    "error": r.error,
                }
                for r in results
            ], indent=2)
        except Exception as e:
            return json.dumps({"error": str(e)})

    @tool
    def get_queue_status() -> str:
        """
        Get current status of the task queue.

        Use this to check how many tasks are pending, the current recursion depth,
        and whether new child agents can be spawned.

        Returns:
            JSON object with queue statistics including:
            - pending: Number of tasks waiting in queue
            - max_queued: Maximum queue capacity
            - max_parallel: Maximum concurrent workers
            - current_depth: Current recursion depth
            - max_depth: Maximum allowed depth
            - can_spawn: Whether new children can be spawned
        """
        return json.dumps({
            "pending": child_process.task_queue.pending_count(),
            "max_queued": child_process.max_queued,
            "max_parallel": child_process.max_parallel,
            "current_depth": child_process._get_current_depth(),
            "max_depth": child_process.max_depth,
            "can_spawn": child_process._get_current_depth() < child_process.max_depth,
        })

    return [
        read_file,
        list_files,
        set_directory,
        count_files,
        delegate_task,
        run_parallel_tasks,
        schedule_tasks,
        execute_scheduled_tasks,
        get_queue_status,
    ]


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

    # Initialize ChildProcess for recursive agent invocation
    child_process = ChildProcess()

    # Add common tools (file ops + child process)
    common_tools = _create_common_tools(file_manager, child_process)
    agent_tools.extend(common_tools)

    # Add memory tools (memory_add, memory_query, memory_verify, memory_reinforce)
    memory_tools = create_memory_tools(file_manager=file_manager)
    agent_tools.extend(memory_tools)

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

Keep responses focused and actionable. Use markdown formatting when it improves readability.

## Task Delegation

For large tasks (10+ files/items), use hierarchical delegation:

- **Queue limit**: 10 tasks per agent
- **Depth limit**: 3 levels of sub-agents
- **Max capacity**: 10 × 10 × 10 = 1,000 items

**Strategy for N items:**
- 1-10 items: Process directly or `run_parallel_tasks`
- 11-100 items: Split into ~10 batches, delegate each
- 100+ items: Split hierarchically (10 → 10 → 10)

**Before delegating**: Use `get_queue_status()` to check `can_spawn`.

**Example (100 files)**:
1. `schedule_tasks` with 10 batch tasks (10 files each)
2. `execute_scheduled_tasks` to run all
3. Each child processes its 10 files via `run_parallel_tasks`
4. Aggregate results for unified response"""

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

    # Initialize ChildProcess for recursive agent invocation
    child_process = ChildProcess()

    # Add common tools (file ops + child process)
    common_tools = _create_common_tools(file_manager, child_process)
    agent_tools.extend(common_tools)

    # Add memory tools (memory_add, memory_query, memory_verify, memory_reinforce)
    memory_tools = create_memory_tools(file_manager=file_manager)
    agent_tools.extend(memory_tools)

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
