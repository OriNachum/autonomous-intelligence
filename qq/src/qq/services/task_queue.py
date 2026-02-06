"""Task queue for scheduling sub-agent work.

Provides a bounded queue that agents use to schedule tasks,
enabling hierarchical task distribution across depth levels.

Usage:
    queue = TaskQueue(child_process, max_queued=10)
    queue.queue_task("Summarize file.md")
    queue.queue_task("Analyze code.py", agent="coder", priority=5)
    results = queue.execute_all()
"""

from __future__ import annotations

import logging
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from enum import Enum
from queue import Empty, Full, Queue
from typing import TYPE_CHECKING, Any, Dict, List, Optional

if TYPE_CHECKING:
    from qq.services.child_process import ChildProcess, ChildResult

logger = logging.getLogger("task_queue")


class TaskStatus(Enum):
    """Status of a queued task."""

    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


@dataclass
class QueuedTask:
    """A task in the queue."""

    task_id: str
    task: str
    agent: str = "default"
    priority: int = 0  # Higher = more urgent
    working_dir: Optional[str] = None
    context: Optional[str] = None  # Initial context for ephemeral notes
    status: TaskStatus = TaskStatus.PENDING
    result: Optional[ChildResult] = None
    metadata: Dict[str, Any] = field(default_factory=dict)


class QueueFullError(Exception):
    """Raised when task queue is at capacity."""

    pass


class TaskQueue:
    """Bounded task queue for sub-agent scheduling.

    Provides a queue-based approach to scheduling child agent tasks,
    allowing agents to batch up work and execute it efficiently.

    Limits:
    - max_queued: Maximum tasks that can be queued (default: 10)
    - max_parallel: Maximum concurrent executions (default: 5)

    Example:
        >>> queue = TaskQueue(child_process, max_queued=10, max_parallel=5)
        >>> queue.queue_task("Process file1.txt")
        'task_0001'
        >>> queue.queue_task("Process file2.txt", priority=10)
        'task_0002'
        >>> results = queue.execute_all()  # Executes high priority first
    """

    def __init__(
        self,
        child_process: ChildProcess,
        max_queued: int = 10,
        max_parallel: int = 5,
    ):
        """Initialize TaskQueue.

        Args:
            child_process: ChildProcess instance for spawning agents.
            max_queued: Maximum tasks that can be queued (default: 10).
            max_parallel: Maximum concurrent task executions (default: 5).
        """
        self.child_process = child_process
        self.max_queued = max_queued
        self.max_parallel = max_parallel

        self._pending: List[QueuedTask] = []
        self._results: Dict[str, QueuedTask] = {}
        self._lock = threading.Lock()
        self._task_counter = 0

    def queue_task(
        self,
        task: str,
        agent: str = "default",
        priority: int = 0,
        working_dir: Optional[str] = None,
        context: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> str:
        """Add a task to the queue.

        Args:
            task: The task description/prompt for the child agent.
            agent: Which agent to use (default: "default").
            priority: Higher numbers execute first (default: 0).
            working_dir: Working directory for child process.
            context: Initial context for child's ephemeral notes.
            metadata: Optional metadata to attach to the task.

        Returns:
            task_id: Unique identifier for tracking.

        Raises:
            QueueFullError: If queue is at max_queued capacity.
        """
        # Validate agent parameter - must be a string, not an Agent object
        if not isinstance(agent, str):
            if hasattr(agent, 'name') and isinstance(agent.name, str):
                logger.warning(f"Agent object passed instead of string, using agent.name: {agent.name}")
                agent = agent.name
            else:
                logger.warning(f"Invalid agent type {type(agent).__name__}, falling back to 'default'")
                agent = "default"

        with self._lock:
            if len(self._pending) >= self.max_queued:
                raise QueueFullError(
                    f"Task queue full (max {self.max_queued}). "
                    "Wait for tasks to complete or increase QQ_MAX_QUEUED."
                )

            self._task_counter += 1
            task_id = f"task_{self._task_counter:04d}"

            queued = QueuedTask(
                task_id=task_id,
                task=task,
                agent=agent,
                priority=priority,
                working_dir=working_dir,
                context=context,
                metadata=metadata or {},
            )

            self._pending.append(queued)
            self._results[task_id] = queued

            logger.debug(f"Queued task {task_id}: {task[:50]}...")
            return task_id

    def queue_batch(
        self,
        tasks: List[Dict[str, Any]],
    ) -> List[str]:
        """Queue multiple tasks at once.

        Args:
            tasks: List of task specs, each with:
                - task: The task description (required)
                - agent: Agent to use (optional, default: "default")
                - priority: Higher numbers first (optional, default: 0)
                - working_dir: Working directory (optional)
                - context: Initial context for ephemeral notes (optional)
                - metadata: Additional metadata (optional)

        Returns:
            List of task_ids in input order.

        Raises:
            QueueFullError: If adding tasks would exceed max_queued.
        """
        task_ids = []
        for spec in tasks:
            task_id = self.queue_task(
                task=spec["task"],
                agent=spec.get("agent", "default"),
                priority=spec.get("priority", 0),
                working_dir=spec.get("working_dir"),
                context=spec.get("context"),
                metadata=spec.get("metadata"),
            )
            task_ids.append(task_id)
        return task_ids

    def execute_all(self, timeout: Optional[int] = None) -> List[ChildResult]:
        """Execute all queued tasks and return results.

        Tasks are executed in priority order (higher priority first).
        Blocks until all tasks complete or timeout.

        Args:
            timeout: Per-task timeout in seconds (uses child_process default if None).

        Returns:
            List of ChildResult objects in priority order (highest first).
        """
        from qq.services.child_process import ChildResult

        with self._lock:
            tasks_to_run = self._pending.copy()
            self._pending.clear()

        if not tasks_to_run:
            return []

        # Sort by priority (higher first)
        tasks_to_run.sort(key=lambda t: -t.priority)

        logger.info(
            f"Executing {len(tasks_to_run)} tasks "
            f"(max_parallel={self.max_parallel})"
        )

        results: List[Optional[ChildResult]] = [None] * len(tasks_to_run)

        with ThreadPoolExecutor(max_workers=self.max_parallel) as executor:
            future_to_idx = {}

            for idx, queued in enumerate(tasks_to_run):
                queued.status = TaskStatus.RUNNING
                future = executor.submit(
                    self.child_process.spawn_agent,
                    task=queued.task,
                    agent=queued.agent,
                    timeout=timeout,
                    working_dir=queued.working_dir,
                    initial_context=queued.context,
                )
                future_to_idx[future] = (idx, queued)

            for future in as_completed(future_to_idx):
                idx, queued = future_to_idx[future]
                try:
                    result = future.result()
                    queued.status = (
                        TaskStatus.COMPLETED if result.success else TaskStatus.FAILED
                    )
                    queued.result = result
                    results[idx] = result
                except Exception as e:
                    logger.error(f"Task {queued.task_id} failed: {e}")
                    queued.status = TaskStatus.FAILED
                    error_result = ChildResult(
                        success=False,
                        output="",
                        error=str(e),
                        agent=queued.agent,
                        task=queued.task,
                    )
                    queued.result = error_result
                    results[idx] = error_result

        return [r for r in results if r is not None]

    def get_status(self, task_id: str) -> Optional[TaskStatus]:
        """Get status of a specific task.

        Args:
            task_id: The task identifier returned from queue_task.

        Returns:
            TaskStatus if task exists, None otherwise.
        """
        if task_id in self._results:
            return self._results[task_id].status
        return None

    def get_result(self, task_id: str) -> Optional[ChildResult]:
        """Get result of a completed task.

        Args:
            task_id: The task identifier returned from queue_task.

        Returns:
            ChildResult if task completed, None if pending or not found.
        """
        if task_id in self._results:
            return self._results[task_id].result
        return None

    def pending_count(self) -> int:
        """Number of tasks waiting in queue."""
        with self._lock:
            return len(self._pending)

    def clear(self) -> int:
        """Clear all pending tasks.

        Returns:
            Number of tasks that were cleared.
        """
        with self._lock:
            count = len(self._pending)
            for task in self._pending:
                task.status = TaskStatus.CANCELLED
            self._pending.clear()
            return count
