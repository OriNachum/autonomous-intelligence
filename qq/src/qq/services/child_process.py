"""Child process management for recursive QQ invocation.

Enables parent QQ agents to spawn child QQ instances as subprocesses
for task delegation and parallel execution.

Supports two execution modes:
1. Immediate execution: delegate_task() / run_parallel()
2. Queue-based execution: queue_task() / execute_queue()
"""

from __future__ import annotations

import json
import logging
import os
import shutil
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any, Dict, List, Optional

if TYPE_CHECKING:
    from qq.services.task_queue import TaskQueue


# Set up logging
def setup_logging():
    """Configure logging for child process module."""
    log_dir = Path(__file__).parent.parent.parent.parent / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    log_file = log_dir / "child_process.log"

    logger = logging.getLogger("child_process")
    logger.setLevel(logging.DEBUG)

    # Only add handlers if none exist
    if not logger.handlers:
        file_handler = logging.FileHandler(log_file)
        file_handler.setLevel(logging.DEBUG)
        file_handler.setFormatter(
            logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
        )
        logger.addHandler(file_handler)

    return logger


logger = setup_logging()


@dataclass
class ChildResult:
    """Result from a child QQ process."""
    success: bool
    output: str
    error: Optional[str] = None
    exit_code: int = 0
    agent: str = "default"
    task: str = ""
    notes_id: Optional[str] = None  # ID of ephemeral notes file used


class ChildProcess:
    """Manages spawning and coordinating child QQ processes.

    All child processes run with --new-session to ensure isolation.
    """

    def __init__(
        self,
        qq_executable: Optional[str] = None,
        default_timeout: Optional[int] = None,
        max_parallel: Optional[int] = None,
        max_depth: Optional[int] = None,
        max_output_size: Optional[int] = None,
        max_queued: Optional[int] = None,
    ):
        """Initialize ChildProcess manager.

        Args:
            qq_executable: Path to qq executable. Auto-detected if None.
            default_timeout: Default timeout in seconds for child processes.
            max_parallel: Maximum concurrent child processes.
            max_depth: Maximum recursion depth.
            max_output_size: Maximum output characters to capture.
            max_queued: Maximum tasks in queue (for queue-based execution).
        """
        self.qq_executable = qq_executable or self._find_qq_executable()
        self.default_timeout = default_timeout or int(os.environ.get("QQ_CHILD_TIMEOUT", "300"))
        self.max_parallel = max_parallel or int(os.environ.get("QQ_MAX_PARALLEL", "5"))
        self.max_depth = max_depth or int(os.environ.get("QQ_MAX_DEPTH", "3"))
        self.max_output_size = max_output_size or int(os.environ.get("QQ_MAX_OUTPUT", "50000"))
        self.max_queued = max_queued or int(os.environ.get("QQ_MAX_QUEUED", "10"))

        # Lazy-initialized task queue
        self._task_queue: Optional[TaskQueue] = None

    def _find_qq_executable(self) -> str:
        """Find the qq executable path."""
        # Try common locations
        candidates = [
            Path.cwd() / "qq",                    # Project root script
            Path(sys.executable).parent / "qq",  # Same venv bin
        ]

        for candidate in candidates:
            if candidate.exists():
                return str(candidate)

        # Check if qq is in PATH
        qq_in_path = shutil.which("qq")
        if qq_in_path:
            return qq_in_path

        # Fallback to module execution
        return f"{sys.executable} -m qq"

    def _get_current_depth(self) -> int:
        """Get current recursion depth from environment."""
        return int(os.environ.get("QQ_RECURSION_DEPTH", "0"))

    def spawn_agent(
        self,
        task: str,
        agent: str = "default",
        timeout: Optional[int] = None,
        working_dir: Optional[str] = None,
        initial_context: Optional[str] = None,
    ) -> ChildResult:
        """Spawn a child QQ agent to handle a task.

        Args:
            task: The task/prompt to send to the child agent.
            agent: Agent name to use (from agents/ directory).
            timeout: Timeout in seconds (uses default if None).
            working_dir: Working directory for child process.
            initial_context: Optional context to seed the child's ephemeral notes.
                             If provided, creates notes.{notes_id}.md with this content.

        Returns:
            ChildResult with output or error.
        """
        from uuid import uuid4
        trace_id = uuid4().hex[:8]

        # Validate agent parameter - must be a string, not an Agent object
        if not isinstance(agent, str):
            # If an Agent object was passed (common LLM tool-call error), extract name or use default
            if hasattr(agent, 'name') and isinstance(agent.name, str):
                logger.warning(f"[{trace_id}] Agent object passed instead of string, using agent.name: {agent.name}")
                agent = agent.name
            else:
                logger.warning(f"[{trace_id}] Invalid agent type {type(agent).__name__}, falling back to 'default'")
                agent = "default"

        # Validate task parameter - must be a string
        if not isinstance(task, str):
            error_msg = f"Task must be a string, got {type(task).__name__}"
            logger.error(f"[{trace_id}] {error_msg}")
            return ChildResult(
                success=False,
                output="",
                error=error_msg,
                exit_code=-1,
                agent=agent if isinstance(agent, str) else "default",
                task=str(task)[:100],
            )

        # Check recursion depth before spawning
        current_depth = self._get_current_depth()
        if current_depth >= self.max_depth:
            error_msg = f"Maximum recursion depth ({self.max_depth}) exceeded"
            logger.warning(f"[{trace_id}] {error_msg}")
            return ChildResult(
                success=False,
                output="",
                error=error_msg,
                exit_code=-1,
                agent=agent,
                task=task,
            )

        timeout = timeout or self.default_timeout
        cmd = self._build_command(task, agent)

        # Generate notes ID and create ephemeral notes if context provided
        notes_id = None
        notes_manager = None
        if initial_context:
            notes_id = f"{trace_id}_{agent}"
            try:
                from qq.memory.notes import NotesManager
                notes_manager = NotesManager.create_ephemeral(
                    notes_id=notes_id,
                    initial_context=initial_context,
                )
                logger.debug(f"[{trace_id}] Created ephemeral notes: notes.{notes_id}.md")
            except Exception as e:
                logger.warning(f"[{trace_id}] Failed to create ephemeral notes: {e}")
                notes_id = None

        logger.info(f"[{trace_id}] Spawning child: agent={agent}, depth={current_depth + 1}, notes_id={notes_id}, task={task[:80]}...")

        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=timeout,
                cwd=working_dir,
                env=self._child_env(notes_id=notes_id),
            )

            # Truncate large outputs
            output = result.stdout.strip()
            if len(output) > self.max_output_size:
                output = output[:self.max_output_size]
                output += f"\n\n[Output truncated at {self.max_output_size} chars]"

            logger.info(f"[{trace_id}] Child completed: success={result.returncode == 0}, exit={result.returncode}")

            # Clean up ephemeral notes after child completes
            if notes_manager:
                try:
                    notes_manager.cleanup()
                    logger.debug(f"[{trace_id}] Cleaned up ephemeral notes: notes.{notes_id}.md")
                except Exception as e:
                    logger.warning(f"[{trace_id}] Failed to cleanup ephemeral notes: {e}")

            return ChildResult(
                success=result.returncode == 0,
                output=output,
                error=result.stderr.strip() if result.stderr else None,
                exit_code=result.returncode,
                agent=agent,
                task=task,
                notes_id=notes_id,
            )

        except subprocess.TimeoutExpired:
            error_msg = f"Child process timed out after {timeout}s"
            logger.error(f"[{trace_id}] {error_msg}")
            # Clean up ephemeral notes on timeout
            if notes_manager:
                notes_manager.cleanup()
            return ChildResult(
                success=False,
                output="",
                error=error_msg,
                exit_code=-1,
                agent=agent,
                task=task,
                notes_id=notes_id,
            )
        except Exception as e:
            logger.error(f"[{trace_id}] Child process error: {e}")
            # Clean up ephemeral notes on error
            if notes_manager:
                notes_manager.cleanup()
            return ChildResult(
                success=False,
                output="",
                error=str(e),
                exit_code=-1,
                agent=agent,
                task=task,
                notes_id=notes_id,
            )

    def run_parallel(
        self,
        tasks: List[Dict[str, Any]],
        timeout: Optional[int] = None,
    ) -> List[ChildResult]:
        """Run multiple child agents in parallel.

        Args:
            tasks: List of task dicts with keys:
                - task: The task description (required)
                - agent: Agent to use (optional, default: "default")
                - working_dir: Working directory (optional)
                - context: Initial context for child's ephemeral notes (optional)
            timeout: Per-task timeout.

        Returns:
            List of ChildResults in same order as input tasks.
        """
        timeout = timeout or self.default_timeout
        results: List[Optional[ChildResult]] = [None] * len(tasks)

        logger.info(f"Running {len(tasks)} tasks in parallel (max_workers={self.max_parallel})")

        with ThreadPoolExecutor(max_workers=self.max_parallel) as executor:
            future_to_idx = {}
            for idx, task_spec in enumerate(tasks):
                future = executor.submit(
                    self.spawn_agent,
                    task=task_spec["task"],
                    agent=task_spec.get("agent", "default"),
                    timeout=timeout,
                    working_dir=task_spec.get("working_dir"),
                    initial_context=task_spec.get("context"),
                )
                future_to_idx[future] = idx

            for future in as_completed(future_to_idx):
                idx = future_to_idx[future]
                try:
                    results[idx] = future.result()
                except Exception as e:
                    logger.error(f"Task {idx} failed with exception: {e}")
                    results[idx] = ChildResult(
                        success=False,
                        output="",
                        error=str(e),
                        agent=tasks[idx].get("agent", "default"),
                        task=tasks[idx]["task"],
                    )

        return results  # type: ignore

    def _build_command(self, task: str, agent: str) -> List[str]:
        """Build subprocess command."""
        if " " in self.qq_executable:
            # Module execution: "python -m qq"
            parts = self.qq_executable.split()
            cmd = parts + ["--agent", agent, "--new-session", "-m", task]
        else:
            cmd = [self.qq_executable, "--agent", agent, "--new-session", "-m", task]
        return cmd

    def _child_env(self, notes_id: Optional[str] = None) -> Dict[str, str]:
        """Get environment for child processes.

        Args:
            notes_id: Optional notes ID for per-agent ephemeral notes.
        """
        env = os.environ.copy()

        # Ensure child gets fresh session
        env.pop("QQ_SESSION_ID", None)

        # Track recursion depth
        current_depth = self._get_current_depth()
        env["QQ_RECURSION_DEPTH"] = str(current_depth + 1)

        # Set per-agent notes ID if provided
        if notes_id:
            env["QQ_NOTES_ID"] = notes_id
        else:
            # Clear parent's notes ID so child uses main notes.md
            env.pop("QQ_NOTES_ID", None)

        # Pass parent session for tracing (optional)
        try:
            from qq.session import get_session_id
            env["QQ_PARENT_SESSION"] = get_session_id()
        except ImportError:
            pass

        return env

    # =========================================================================
    # Queue-based execution methods
    # =========================================================================

    @property
    def task_queue(self) -> TaskQueue:
        """Lazy-initialized task queue for batch scheduling.

        Returns:
            TaskQueue instance configured with this ChildProcess.
        """
        if self._task_queue is None:
            from qq.services.task_queue import TaskQueue

            self._task_queue = TaskQueue(
                child_process=self,
                max_queued=self.max_queued,
                max_parallel=self.max_parallel,
            )
        return self._task_queue

    def queue_task(
        self,
        task: str,
        agent: str = "default",
        priority: int = 0,
        working_dir: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> str:
        """Queue a task for later batch execution.

        Use this when you want to schedule multiple tasks and execute
        them all at once with execute_queue().

        Args:
            task: The task/prompt for the child agent.
            agent: Which agent to use (default: "default").
            priority: Higher numbers execute first (default: 0).
            working_dir: Working directory for child process.
            metadata: Optional metadata to attach.

        Returns:
            task_id: Unique identifier for tracking.

        Raises:
            QueueFullError: If queue is at max_queued capacity.
        """
        return self.task_queue.queue_task(
            task=task,
            agent=agent,
            priority=priority,
            working_dir=working_dir,
            metadata=metadata,
        )

    def queue_batch(self, tasks: List[Dict[str, Any]]) -> List[str]:
        """Queue multiple tasks for batch execution.

        Args:
            tasks: List of task specs with keys:
                - task: The task description (required)
                - agent: Agent to use (optional)
                - priority: Higher first (optional)
                - working_dir: Working dir (optional)

        Returns:
            List of task_ids in input order.
        """
        return self.task_queue.queue_batch(tasks)

    def execute_queue(self, timeout: Optional[int] = None) -> List[ChildResult]:
        """Execute all queued tasks and return results.

        Tasks are executed in priority order (higher first).

        Args:
            timeout: Per-task timeout (uses default_timeout if None).

        Returns:
            List of ChildResult objects.
        """
        return self.task_queue.execute_all(timeout=timeout or self.default_timeout)
