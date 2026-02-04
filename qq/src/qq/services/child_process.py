"""Child process management for recursive QQ invocation.

Enables parent QQ agents to spawn child QQ instances as subprocesses
for task delegation and parallel execution.
"""

import os
import sys
import shutil
import subprocess
import json
import logging
from pathlib import Path
from typing import Optional, List, Dict, Any
from dataclasses import dataclass
from concurrent.futures import ThreadPoolExecutor, as_completed


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
    ):
        """Initialize ChildProcess manager.

        Args:
            qq_executable: Path to qq executable. Auto-detected if None.
            default_timeout: Default timeout in seconds for child processes.
            max_parallel: Maximum concurrent child processes.
            max_depth: Maximum recursion depth.
            max_output_size: Maximum output characters to capture.
        """
        self.qq_executable = qq_executable or self._find_qq_executable()
        self.default_timeout = default_timeout or int(os.environ.get("QQ_CHILD_TIMEOUT", "300"))
        self.max_parallel = max_parallel or int(os.environ.get("QQ_MAX_PARALLEL", "5"))
        self.max_depth = max_depth or int(os.environ.get("QQ_MAX_DEPTH", "3"))
        self.max_output_size = max_output_size or int(os.environ.get("QQ_MAX_OUTPUT", "50000"))

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
    ) -> ChildResult:
        """Spawn a child QQ agent to handle a task.

        Args:
            task: The task/prompt to send to the child agent.
            agent: Agent name to use (from agents/ directory).
            timeout: Timeout in seconds (uses default if None).
            working_dir: Working directory for child process.

        Returns:
            ChildResult with output or error.
        """
        from uuid import uuid4
        trace_id = uuid4().hex[:8]

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

        logger.info(f"[{trace_id}] Spawning child: agent={agent}, depth={current_depth + 1}, task={task[:80]}...")

        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=timeout,
                cwd=working_dir,
                env=self._child_env(),
            )

            # Truncate large outputs
            output = result.stdout.strip()
            if len(output) > self.max_output_size:
                output = output[:self.max_output_size]
                output += f"\n\n[Output truncated at {self.max_output_size} chars]"

            logger.info(f"[{trace_id}] Child completed: success={result.returncode == 0}, exit={result.returncode}")

            return ChildResult(
                success=result.returncode == 0,
                output=output,
                error=result.stderr.strip() if result.stderr else None,
                exit_code=result.returncode,
                agent=agent,
                task=task,
            )

        except subprocess.TimeoutExpired:
            error_msg = f"Child process timed out after {timeout}s"
            logger.error(f"[{trace_id}] {error_msg}")
            return ChildResult(
                success=False,
                output="",
                error=error_msg,
                exit_code=-1,
                agent=agent,
                task=task,
            )
        except Exception as e:
            logger.error(f"[{trace_id}] Child process error: {e}")
            return ChildResult(
                success=False,
                output="",
                error=str(e),
                exit_code=-1,
                agent=agent,
                task=task,
            )

    def run_parallel(
        self,
        tasks: List[Dict[str, Any]],
        timeout: Optional[int] = None,
    ) -> List[ChildResult]:
        """Run multiple child agents in parallel.

        Args:
            tasks: List of task dicts with keys: task, agent (optional), working_dir (optional)
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

    def _child_env(self) -> Dict[str, str]:
        """Get environment for child processes."""
        env = os.environ.copy()

        # Ensure child gets fresh session
        env.pop("QQ_SESSION_ID", None)

        # Track recursion depth
        current_depth = self._get_current_depth()
        env["QQ_RECURSION_DEPTH"] = str(current_depth + 1)

        # Pass parent session for tracing (optional)
        try:
            from qq.session import get_session_id
            env["QQ_PARENT_SESSION"] = get_session_id()
        except ImportError:
            pass

        return env
