"""Agent loader - loads agents from agents/<name>/ directories.

Updated for parallel execution support:
- FileManager uses session-isolated state directories
- Default agent creation is atomic (race-safe)
- ChildProcess enables recursive agent invocation
"""

import json
import logging
import os
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional, Tuple, List

from strands import Agent, tool
from strands.agent.conversation_manager import SlidingWindowConversationManager
from strands.models import OpenAIModel

from qq.session import get_session_dir
from qq.services.file_manager import FileManager
from qq.services.child_process import ChildProcess
from qq.services.task_queue import QueueFullError
from qq.services.summarizer import summarize_if_needed
from qq.services.output_guard import guard_output
from qq.services.memory_tools import create_memory_tools
from qq.services.analyzer import create_analyzer_tool


logger = logging.getLogger("qq.agents")


class ChildCallbackHandler:
    """Callback handler for child agents that suppresses thinking blocks and verbose output.

    Child agent stdout is captured by the parent as the child's result.
    Printing reasoningText (<think> blocks) and verbose tool-use info
    bloats that captured output, so we suppress them here.
    """

    def __init__(self):
        self.tool_count = 0

    def __call__(self, **kwargs: Any) -> None:
        data = kwargs.get("data", "")
        complete = kwargs.get("complete", False)

        # Suppress reasoningText entirely — parent doesn't need it

        # Print only the final text output (the actual answer)
        if data:
            print(data, end="" if not complete else "\n")

        # Count tools silently (no verbose printing)
        tool_use = kwargs.get("event", {}).get("contentBlockStart", {}).get("start", {}).get("toolUse")
        if tool_use:
            self.tool_count += 1

        if complete and data:
            print("\n")


def _get_conversation_manager() -> SlidingWindowConversationManager:
    """Create a depth-aware conversation manager.

    Children get a smaller window with per-turn management to prevent
    context overflow during multi-tool loops.
    """
    depth = int(os.environ.get("QQ_RECURSION_DEPTH", "0"))
    if depth > 0:
        return SlidingWindowConversationManager(
            window_size=8, per_turn=True, should_truncate_results=True
        )
    return SlidingWindowConversationManager(
        window_size=20, per_turn=True, should_truncate_results=True
    )


def _get_callback_handler():
    """Return ChildCallbackHandler for child agents, None (default) for root."""
    depth = int(os.environ.get("QQ_RECURSION_DEPTH", "0"))
    if depth > 0:
        return ChildCallbackHandler()
    return None


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


def _get_ancestor_context() -> str:
    """Build ancestor request chain context for worker agents.

    Reads QQ_ANCESTOR_REQUESTS env var (JSON array of predecessor requests)
    and formats it so the agent understands the full lineage of requests.
    """
    import json as _json
    raw = os.environ.get("QQ_ANCESTOR_REQUESTS", "[]")
    try:
        ancestors = _json.loads(raw)
    except (ValueError, TypeError):
        ancestors = []

    if not ancestors:
        return ""

    lines = ["\n\n## Request Lineage\n"]
    lines.append("Your task originates from the following chain of requests (root → parent):\n")
    for i, req in enumerate(ancestors):
        depth_label = "Root request" if i == 0 else f"Level {i} request"
        # Truncate very long requests for prompt efficiency
        display = req if len(req) <= 300 else req[:300] + "..."
        lines.append(f"- **{depth_label}**: {display}")

    lines.append("\nStay anchored to the original intent. Your subtask should serve the root request.")
    return "\n".join(lines)


def _get_depth_context() -> str:
    """Generate depth-aware prompt section based on current recursion depth.

    Returns role-specific instructions depending on whether this agent is
    a root coordinator, middle worker, or leaf worker.
    """
    current_depth = int(os.environ.get("QQ_RECURSION_DEPTH", "0"))
    max_depth = int(os.environ.get("QQ_MAX_DEPTH", "3"))

    if current_depth == 0:
        return """

## Agent Role: Coordinator (Root)

You are the top-level agent. Your primary role is to orchestrate and delegate.

- For any task spanning 2+ files or multiple distinct concerns, delegate rather than doing it yourself.
- Break work into clear subtasks and use delegation tools (`delegate_task`, `run_parallel_tasks`, `schedule_tasks`).
- **Use resource ranges**: Assign ranges of items to each task via `variables.resource_range` (e.g. `"file1..file10"`)
  instead of creating one task per item. This is more efficient and reduces scheduling overhead.
- Focus on planning, splitting work by ranges, aggregating results, and presenting to the user.
- Only do single-file or simple tasks directly.
- Always check `get_queue_status()` before delegating."""

    ancestor_context = _get_ancestor_context()

    if current_depth >= max_depth:
        return f"""

## Agent Role: Leaf Worker (depth {current_depth}/{max_depth})

You are a leaf worker agent — you cannot delegate further.

- Do all work directly. Do not attempt to use delegation tools.
- **Be extremely concise** — your output goes back to a parent agent with limited context.
- Output ONLY the final result. No preamble, no explanations of your process, no verbose reasoning.
- Keep your response under 500 words. Use bullet points for lists.
- If the task is too large for you to handle alone, complete what you can and clearly note what remains.{ancestor_context}"""

    else:
        return f"""

## Agent Role: Worker (depth {current_depth}/{max_depth})

You are a delegated worker agent.

- Focus on completing your assigned subtask efficiently.
- You can delegate if your subtask is large (10+ items), but prefer direct execution.
- **Be extremely concise** — your parent agent has limited context and must process multiple results.
- Output ONLY the final result. No preamble, no explanations of your process, no verbose reasoning.
- Keep your response under 500 words. Use bullet points for lists.{ancestor_context}"""


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


def _build_variables_context(existing_context: str, variables_json: str) -> str:
    """Build enriched context string from task variables.

    Parses the variables JSON and formats resource/resource_range/resource_instructions
    into a context block that the child agent can understand and act on.

    Args:
        existing_context: Any pre-existing context string.
        variables_json: JSON string with variable definitions, or empty string.

    Returns:
        Combined context string with variable information prepended.
    """
    if not variables_json:
        return existing_context

    try:
        variables = json.loads(variables_json) if isinstance(variables_json, str) else variables_json
    except (json.JSONDecodeError, TypeError):
        return existing_context

    if not isinstance(variables, dict):
        return existing_context

    parts = []

    resource = variables.get("resource")
    resource_range = variables.get("resource_range")
    resource_instructions = variables.get("resource_instructions")

    if resource_range:
        parts.append(f"## Assigned Resource Range\n\nYou are assigned the range: `{resource_range}`")
        parts.append('The range uses ".." as a separator between the first and last items.')
        parts.append("You must process ALL items within this range, not just the endpoints.")
    elif resource:
        parts.append(f"## Assigned Resource\n\nYou are assigned: `{resource}`")

    if resource_instructions:
        parts.append(f"\n**Resource instructions**: {resource_instructions}")

    if not parts:
        return existing_context

    variables_block = "\n".join(parts)

    if existing_context:
        return f"{variables_block}\n\n{existing_context}"
    return variables_block


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
        # Cap lines for child agents to reduce output size
        depth = int(os.environ.get("QQ_RECURSION_DEPTH", "0"))
        max_lines = 50 if depth > 0 else 100
        num_lines = min(num_lines, max_lines)
        result = file_manager.read_file(path, start_line, num_lines)
        return guard_output(result, "read_file")

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
    def get_current_directory() -> str:
        """
        Get the current working directory for file operations.

        Returns:
            The absolute path of the current working directory.
        """
        return file_manager.cwd

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
    def delegate_task(task: str, agent: str = "default", context: str = "", variables: str = "") -> str:
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
            variables: JSON object with task variables. Supports:
                - resource: A single item to process (e.g. a filename, an ID).
                - resource_range: A range of items using ".." separator (e.g. "file1.py..file10.py",
                  "1..50"). The child agent will process all items in the range.
                - resource_instructions: Instructions for how to interpret/enumerate the resource or range.
                  E.g. "These are Python files in src/. Process each file by running lint checks."

                Prefer resource_range over creating many individual tasks. One task with a range
                is more efficient than N tasks with one resource each.

                Example: '{"resource_range": "auth.py..validator.py", "resource_instructions": "Analyze each .py file in src/services/ alphabetically from auth.py through validator.py"}'

        Returns:
            The child agent's response (summarized if large).
        """
        # Build enriched context from variables
        effective_context = _build_variables_context(context, variables)

        result = child_process.spawn_agent(
            task=task,
            agent=agent,
            initial_context=effective_context if effective_context else None,
            working_dir=file_manager.cwd,
        )
        if result.success:
            # Summarize large outputs to prevent token overflow
            output = summarize_if_needed(result.output, task)
            return guard_output(output, "delegate_task")
        else:
            return f"Child agent error: {result.error}"

    @tool
    def run_parallel_tasks(tasks_json: str) -> str:
        """
        Run multiple tasks in parallel using child QQ agents.

        Use this for batch operations where tasks don't depend on each other.

        IMPORTANT: Prefer fewer tasks with resource_range over many tasks with single resources.
        Instead of 10 tasks for 10 files, create 2-3 tasks each covering a range of files.

        Args:
            tasks_json: JSON array of task objects, each with:
                - task: The task description (required)
                - agent: Agent to use (optional, default: "default")
                - context: Initial context for child's working memory (optional)
                - variables: Object with resource assignment (optional):
                    - resource: Single item to process
                    - resource_range: Range using ".." (e.g. "file_a.py..file_m.py")
                    - resource_instructions: How to interpret the resource/range

        Example with resource ranges (preferred):
            tasks_json = '[
                {"task": "Lint check Python files", "variables": {"resource_range": "auth.py..handlers.py", "resource_instructions": "All .py files in src/ alphabetically from auth.py through handlers.py"}},
                {"task": "Lint check Python files", "variables": {"resource_range": "models.py..views.py", "resource_instructions": "All .py files in src/ alphabetically from models.py through views.py"}}
            ]'

        Returns:
            JSON array of results with task, agent, success, output (summarized), and error fields.
        """
        try:
            tasks = json.loads(tasks_json)
            if not isinstance(tasks, list):
                return "Error: tasks_json must be a JSON array"

            # Enrich each task's context with variables and inject working dir
            for t in tasks:
                t.setdefault("working_dir", file_manager.cwd)
                variables = t.pop("variables", None)
                if variables:
                    existing_context = t.get("context", "")
                    t["context"] = _build_variables_context(
                        existing_context,
                        json.dumps(variables) if isinstance(variables, dict) else str(variables),
                    )

            results = child_process.run_parallel(tasks)
            output = json.dumps([
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
            return guard_output(output, "run_parallel_tasks")
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

        IMPORTANT: Prefer fewer tasks with resource_range over many tasks with single resources.
        Instead of 10 tasks for 10 files, create 2-3 tasks each covering a range of files.

        Tasks are executed in priority order when execute_scheduled_tasks() is called.

        Args:
            tasks_json: JSON array of task objects, each with:
                - task: The task description (required)
                - agent: Agent to use (optional, default: "default")
                - priority: Higher numbers execute first (optional, default: 0)
                - context: Initial context for child's working memory (optional)
                - variables: Object with resource assignment (optional):
                    - resource: Single item to process
                    - resource_range: Range using ".." (e.g. "batch1..batch5")
                    - resource_instructions: How to interpret the resource/range

        Example:
            schedule_tasks('[
                {"task": "Process files", "priority": 2, "variables": {"resource_range": "file01.txt..file10.txt", "resource_instructions": "Files numbered 01-10 in data/"}},
                {"task": "Process files", "priority": 1, "variables": {"resource_range": "file11.txt..file20.txt", "resource_instructions": "Files numbered 11-20 in data/"}}
            ]')

        Returns:
            JSON object with queued count, task_ids, and pending count.
        """
        try:
            tasks = json.loads(tasks_json)
            if not isinstance(tasks, list):
                return json.dumps({"error": "tasks_json must be a JSON array"})

            # Enrich each task's context with variables and inject working dir
            for t in tasks:
                t.setdefault("working_dir", file_manager.cwd)
                variables = t.pop("variables", None)
                if variables:
                    existing_context = t.get("context", "")
                    t["context"] = _build_variables_context(
                        existing_context,
                        json.dumps(variables) if isinstance(variables, dict) else str(variables),
                    )

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

            output = json.dumps([
                {
                    "task": r.task,
                    "agent": r.agent,
                    "success": r.success,
                    "output": summarize_if_needed(r.output, r.task) if r.success else r.output,
                    "error": r.error,
                }
                for r in results
            ], indent=2)
            return guard_output(output, "execute_scheduled_tasks")
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
        get_current_directory,
        count_files,
        delegate_task,
        run_parallel_tasks,
        schedule_tasks,
        execute_scheduled_tasks,
        get_queue_status,
    ]


def load_agent(name: str, cwd: Optional[str] = None) -> Tuple[Agent, FileManager]:
    """
    Load an agent by name from the agents directory.

    Args:
        name: Agent name (directory under agents/).
        cwd: Initial working directory. If None, uses os.getcwd().

    Returns:
        Tuple of (Agent, FileManager) - FileManager is needed for history capture
    """
    agents_dir = find_agents_dir()
    agent_dir = agents_dir / name

    # Check for agent directory
    if not agent_dir.exists():
        if name == "default":
            # Create default agent
            return _create_default_agent(agent_dir, cwd=cwd)
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

    # Append depth-aware role context
    system_prompt += _get_depth_context()

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
    file_manager = FileManager(session_dir, cwd=cwd)

    # Initialize ChildProcess for recursive agent invocation
    child_process = ChildProcess()

    # Add common tools (file ops + child process)
    common_tools = _create_common_tools(file_manager, child_process)
    agent_tools.extend(common_tools)

    # Add memory tools (memory_add, memory_query, memory_verify, memory_reinforce)
    memory_tools = create_memory_tools(file_manager=file_manager)
    agent_tools.extend(memory_tools)

    # Add analyzer tool (analyze_files)
    analyzer_tool = create_analyzer_tool(file_manager=file_manager)
    agent_tools.append(analyzer_tool)

    # Instantiate Strands Agent with depth-aware conversation management
    conv_mgr = _get_conversation_manager()
    callback_handler = _get_callback_handler()
    agent_kwargs = dict(
        name=name,
        system_prompt=system_prompt,
        model=model,
        tools=agent_tools,
        conversation_manager=conv_mgr,
    )
    if callback_handler is not None:
        agent_kwargs["callback_handler"] = callback_handler
    agent = Agent(**agent_kwargs)

    return agent, file_manager


def _create_default_agent(agent_dir: Path, cwd: Optional[str] = None) -> Tuple[Agent, FileManager]:
    """Create and return the default agent with atomic file creation."""
    system_prompt = """You are a helpful AI assistant.

You are friendly, knowledgeable, and concise. You help users with their questions and tasks.

When using tools, explain what you're doing and share the results clearly.

Keep responses focused and actionable. Use markdown formatting when it improves readability.

## Task Delegation

For multi-file tasks (2+ files/items), use hierarchical delegation:

- **Queue limit**: 10 tasks per agent
- **Depth limit**: 3 levels of sub-agents
- **Max capacity**: 10 × 10 × 10 = 1,000 items

**Resource ranges**: Use `variables` with `resource_range` to assign ranges of items to each task
instead of creating one task per item. A range uses `..` as separator (e.g. `"file_a.py..file_m.py"`).
Add `resource_instructions` to tell the child how to enumerate items in the range.

**Strategy for N items:**
- 1 item: Process directly
- 2-10 items: Use `delegate_task` with `resource_range` covering all items
- 11-100 items: Split into ~10 range-based batches, delegate each
- 100+ items: Split hierarchically (10 → 10 → 10), each with resource ranges

**Before delegating**: Use `get_queue_status()` to check `can_spawn`.

**Example (30 files in src/, alphabetically a.py through z.py)**:
1. `schedule_tasks` with 3 tasks, each with a `resource_range`:
   - `{"task": "Analyze files", "variables": {"resource_range": "a.py..j.py", "resource_instructions": "All .py files in src/ alphabetically from a.py through j.py"}}`
   - `{"task": "Analyze files", "variables": {"resource_range": "k.py..t.py", "resource_instructions": "All .py files in src/ alphabetically from k.py through t.py"}}`
   - `{"task": "Analyze files", "variables": {"resource_range": "u.py..z.py", "resource_instructions": "All .py files in src/ alphabetically from u.py through z.py"}}`
2. `execute_scheduled_tasks` to run all
3. Aggregate results for unified response"""

    # Append depth-aware role context
    system_prompt += _get_depth_context()

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
    file_manager = FileManager(session_dir, cwd=cwd)

    # Initialize ChildProcess for recursive agent invocation
    child_process = ChildProcess()

    # Add common tools (file ops + child process)
    common_tools = _create_common_tools(file_manager, child_process)
    agent_tools.extend(common_tools)

    # Add memory tools (memory_add, memory_query, memory_verify, memory_reinforce)
    memory_tools = create_memory_tools(file_manager=file_manager)
    agent_tools.extend(memory_tools)

    # Add analyzer tool (analyze_files)
    analyzer_tool = create_analyzer_tool(file_manager=file_manager)
    agent_tools.append(analyzer_tool)

    # Depth-aware conversation management and callback handling
    conv_mgr = _get_conversation_manager()
    callback_handler = _get_callback_handler()
    agent_kwargs = dict(
        name="default",
        system_prompt=system_prompt,
        model=model,
        tools=agent_tools,
        conversation_manager=conv_mgr,
    )
    if callback_handler is not None:
        agent_kwargs["callback_handler"] = callback_handler
    agent = Agent(**agent_kwargs)

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
