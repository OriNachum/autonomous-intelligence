# Sub-Agent Call Queue System

> **Status**: Planned
> **Goal**: Enable processing hundreds of files in a single request through hierarchical task queuing

## Executive Summary

Implement a task queue system that allows agents to schedule up to 10 tasks, combined with 3 levels of sub-agent depth, enabling up to 10^3 = 1,000 sub-tasks per request.

---

## Current State Analysis

### Depth Limit Clarification

**Question**: Is the limit 2 or 3 sub-agent calls, and does it include or exclude the initial agent?

**Answer**: The current implementation allows **3 sub-agent calls** (excluding the initial agent).

```
┌────────────────────────────────────────────────────────────────────┐
│  DEPTH COUNTING (max_depth=3)                                       │
├────────────────────────────────────────────────────────────────────┤
│                                                                     │
│  User Request                                                       │
│       │                                                             │
│       ▼                                                             │
│  ┌─────────────┐                                                    │
│  │ Root Agent  │  QQ_RECURSION_DEPTH=0 (not set)                   │
│  │  depth=0    │  ✓ CAN spawn children                             │
│  └──────┬──────┘                                                    │
│         │ spawn_agent() → 0 >= 3? NO                               │
│         ▼                                                           │
│  ┌─────────────┐                                                    │
│  │ Child L1    │  QQ_RECURSION_DEPTH=1                             │
│  │  depth=1    │  ✓ CAN spawn children                             │
│  └──────┬──────┘                                                    │
│         │ spawn_agent() → 1 >= 3? NO                               │
│         ▼                                                           │
│  ┌─────────────┐                                                    │
│  │ Child L2    │  QQ_RECURSION_DEPTH=2                             │
│  │  depth=2    │  ✓ CAN spawn children                             │
│  └──────┬──────┘                                                    │
│         │ spawn_agent() → 2 >= 3? NO                               │
│         ▼                                                           │
│  ┌─────────────┐                                                    │
│  │ Child L3    │  QQ_RECURSION_DEPTH=3                             │
│  │  depth=3    │  ✗ CANNOT spawn (3 >= 3 = BLOCKED)                │
│  └─────────────┘                                                    │
│                                                                     │
│  TOTAL: 4 agent levels (root + 3 children generations)             │
│  SUB-AGENT CALLS: 3 (depth 0→1, 1→2, 2→3)                          │
│  Initial agent: NOT counted as sub-agent call                       │
└────────────────────────────────────────────────────────────────────┘
```

**Code reference** (`src/qq/services/child_process.py:129-141`):
```python
current_depth = self._get_current_depth()
if current_depth >= self.max_depth:
    error_msg = f"Maximum recursion depth ({self.max_depth}) exceeded"
    return ChildResult(success=False, error=error_msg, ...)
```

### Current Parallel Execution

| Parameter | Default | Env Variable |
|-----------|---------|--------------|
| Max Parallel | 5 | `QQ_MAX_PARALLEL` |
| Max Depth | 3 | `QQ_MAX_DEPTH` |
| Timeout | 300s | `QQ_CHILD_TIMEOUT` |
| Max Output | 50KB | `QQ_MAX_OUTPUT` |

**Current capacity**: 5 parallel × 3 depth = 5^3 = 125 theoretical sub-tasks

### Limitations of Current Approach

1. **No queue/scheduling**: Tasks submitted directly to ThreadPoolExecutor
2. **No batching**: Can't schedule more than `max_parallel` before blocking
3. **No priority**: FIFO only, no task prioritization
4. **No backpressure**: Parent waits for all children before continuing
5. **Memory pressure**: Large parallel batches hold all results in memory

---

## Proposed Architecture

### Task Queue Design

```
┌─────────────────────────────────────────────────────────────────────┐
│  TASK QUEUE ARCHITECTURE                                            │
├─────────────────────────────────────────────────────────────────────┤
│                                                                     │
│  ┌─────────────┐                                                    │
│  │ Parent Agent│                                                    │
│  └──────┬──────┘                                                    │
│         │ queue_tasks([task1, ..., task10])                        │
│         ▼                                                           │
│  ┌─────────────────────────────────────────────────────────────┐   │
│  │                    TaskQueue                                  │   │
│  │  ┌─────────────────────────────────────────────────────────┐ │   │
│  │  │ Pending Queue (max 10)                                   │ │   │
│  │  │ [T1][T2][T3][T4][T5][T6][T7][T8][T9][T10]               │ │   │
│  │  └─────────────────────────────────────────────────────────┘ │   │
│  │                          │                                    │   │
│  │                          ▼                                    │   │
│  │  ┌─────────────────────────────────────────────────────────┐ │   │
│  │  │ Executor Pool (max 5 workers)                           │ │   │
│  │  │ [Worker1][Worker2][Worker3][Worker4][Worker5]           │ │   │
│  │  └─────────────────────────────────────────────────────────┘ │   │
│  │                          │                                    │   │
│  │                          ▼                                    │   │
│  │  ┌─────────────────────────────────────────────────────────┐ │   │
│  │  │ Results Store                                           │ │   │
│  │  │ {task_id: ChildResult, ...}                             │ │   │
│  │  └─────────────────────────────────────────────────────────┘ │   │
│  └─────────────────────────────────────────────────────────────┘   │
│                                                                     │
└─────────────────────────────────────────────────────────────────────┘
```

### Hierarchical Task Distribution

With queue size of 10 and depth of 3:

```
Level 0 (Root):        1 agent can queue → 10 tasks
Level 1 (Children):   10 agents can queue → 100 tasks
Level 2 (Grandchild): 100 agents can queue → 1,000 tasks
Level 3 (Terminal):   1,000 agents execute (cannot spawn)
                      ─────────────────────────────────
                      TOTAL CAPACITY: 1,000 leaf tasks
```

---

## Implementation Plan

### Phase 1: TaskQueue Core

**File**: `src/qq/services/task_queue.py`

```python
"""Task queue for scheduling sub-agent work.

Provides a bounded queue that agents use to schedule tasks,
enabling hierarchical task distribution across depth levels.
"""

import asyncio
import threading
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional, List, Dict, Any, Callable
from concurrent.futures import ThreadPoolExecutor, Future
from queue import Queue, Full
import logging

logger = logging.getLogger("task_queue")


class TaskStatus(Enum):
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
    status: TaskStatus = TaskStatus.PENDING
    result: Optional["ChildResult"] = None
    metadata: Dict[str, Any] = field(default_factory=dict)


class TaskQueue:
    """Bounded task queue for sub-agent scheduling.

    Limits:
    - max_queued: Maximum tasks that can be queued (default: 10)
    - max_parallel: Maximum concurrent executions (default: 5)
    """

    def __init__(
        self,
        child_process: "ChildProcess",
        max_queued: int = 10,
        max_parallel: int = 5,
    ):
        self.child_process = child_process
        self.max_queued = max_queued
        self.max_parallel = max_parallel

        self._queue: Queue[QueuedTask] = Queue(maxsize=max_queued)
        self._results: Dict[str, QueuedTask] = {}
        self._executor: Optional[ThreadPoolExecutor] = None
        self._futures: Dict[str, Future] = {}
        self._lock = threading.Lock()
        self._task_counter = 0

    def queue_task(
        self,
        task: str,
        agent: str = "default",
        priority: int = 0,
        working_dir: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> str:
        """Add a task to the queue.

        Returns:
            task_id: Unique identifier for tracking

        Raises:
            QueueFullError: If queue is at capacity
        """
        with self._lock:
            self._task_counter += 1
            task_id = f"task_{self._task_counter:04d}"

        queued = QueuedTask(
            task_id=task_id,
            task=task,
            agent=agent,
            priority=priority,
            working_dir=working_dir,
            metadata=metadata or {},
        )

        try:
            self._queue.put_nowait(queued)
            self._results[task_id] = queued
            logger.debug(f"Queued task {task_id}: {task[:50]}...")
            return task_id
        except Full:
            raise QueueFullError(
                f"Task queue full (max {self.max_queued}). "
                "Wait for tasks to complete or increase QQ_MAX_QUEUED."
            )

    def queue_batch(
        self,
        tasks: List[Dict[str, Any]],
    ) -> List[str]:
        """Queue multiple tasks at once.

        Args:
            tasks: List of task specs with keys: task, agent, priority, working_dir

        Returns:
            List of task_ids in input order
        """
        task_ids = []
        for spec in tasks:
            task_id = self.queue_task(
                task=spec["task"],
                agent=spec.get("agent", "default"),
                priority=spec.get("priority", 0),
                working_dir=spec.get("working_dir"),
                metadata=spec.get("metadata"),
            )
            task_ids.append(task_id)
        return task_ids

    def execute_all(self, timeout: Optional[int] = None) -> List["ChildResult"]:
        """Execute all queued tasks and return results.

        Blocks until all tasks complete or timeout.
        """
        tasks_to_run = []
        while not self._queue.empty():
            tasks_to_run.append(self._queue.get_nowait())

        if not tasks_to_run:
            return []

        # Sort by priority (higher first)
        tasks_to_run.sort(key=lambda t: -t.priority)

        results = [None] * len(tasks_to_run)

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
                )
                future_to_idx[future] = (idx, queued)

            for future in as_completed(future_to_idx, timeout=timeout):
                idx, queued = future_to_idx[future]
                try:
                    result = future.result()
                    queued.status = TaskStatus.COMPLETED if result.success else TaskStatus.FAILED
                    queued.result = result
                    results[idx] = result
                except Exception as e:
                    queued.status = TaskStatus.FAILED
                    results[idx] = ChildResult(
                        success=False,
                        output="",
                        error=str(e),
                        agent=queued.agent,
                        task=queued.task,
                    )

        return results

    def get_status(self, task_id: str) -> Optional[TaskStatus]:
        """Get status of a specific task."""
        if task_id in self._results:
            return self._results[task_id].status
        return None

    def get_result(self, task_id: str) -> Optional["ChildResult"]:
        """Get result of a completed task."""
        if task_id in self._results:
            return self._results[task_id].result
        return None

    def pending_count(self) -> int:
        """Number of tasks waiting in queue."""
        return self._queue.qsize()

    def clear(self):
        """Clear all pending tasks."""
        while not self._queue.empty():
            try:
                task = self._queue.get_nowait()
                task.status = TaskStatus.CANCELLED
            except:
                break


class QueueFullError(Exception):
    """Raised when task queue is at capacity."""
    pass
```

### Phase 2: Integration with ChildProcess

**File**: `src/qq/services/child_process.py` (modifications)

```python
class ChildProcess:
    def __init__(
        self,
        # ... existing params ...
        max_queued: Optional[int] = None,
    ):
        # ... existing init ...
        self.max_queued = max_queued or int(os.environ.get("QQ_MAX_QUEUED", "10"))
        self._task_queue: Optional[TaskQueue] = None

    @property
    def task_queue(self) -> TaskQueue:
        """Lazy-initialized task queue."""
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
        **kwargs,
    ) -> str:
        """Queue a task for later execution."""
        return self.task_queue.queue_task(
            task=task,
            agent=agent,
            priority=priority,
            **kwargs,
        )

    def queue_batch(self, tasks: List[Dict[str, Any]]) -> List[str]:
        """Queue multiple tasks."""
        return self.task_queue.queue_batch(tasks)

    def execute_queue(self, timeout: Optional[int] = None) -> List[ChildResult]:
        """Execute all queued tasks."""
        return self.task_queue.execute_all(timeout=timeout or self.default_timeout)
```

### Phase 3: New Tools

**File**: `src/qq/agents/__init__.py` (add new tools)

```python
@tool
def schedule_tasks(tasks_json: str) -> str:
    """
    Schedule multiple tasks for batch execution.

    This queues tasks without immediately executing them, allowing you to
    build up a batch of work before running it all at once. Use this when
    you have many tasks to process and want efficient scheduling.

    Args:
        tasks_json: JSON array of task objects, each with:
            - task: The task description (required)
            - agent: Agent to use (optional, default: "default")
            - priority: Higher numbers execute first (optional, default: 0)

    Example:
        schedule_tasks('[
            {"task": "Process file1.py", "priority": 2},
            {"task": "Process file2.py", "priority": 1},
            {"task": "Process file3.py"}
        ]')

    Returns:
        JSON object with task_ids for tracking
    """
    try:
        tasks = json.loads(tasks_json)
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
        JSON array of results in the order tasks were queued
    """
    try:
        results = child_process.execute_queue()
        return json.dumps([
            {
                "task": r.task,
                "agent": r.agent,
                "success": r.success,
                "output": r.output,
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

    Returns:
        JSON object with queue statistics
    """
    return json.dumps({
        "pending": child_process.task_queue.pending_count(),
        "max_queued": child_process.max_queued,
        "max_parallel": child_process.max_parallel,
        "current_depth": child_process._get_current_depth(),
        "max_depth": child_process.max_depth,
        "can_spawn": child_process._get_current_depth() < child_process.max_depth,
    })
```

### Phase 4: Configuration Updates

**Environment Variables**

| Variable | Default | Description |
|----------|---------|-------------|
| `QQ_MAX_QUEUED` | 10 | Maximum tasks in queue |
| `QQ_MAX_PARALLEL` | 5 | Maximum concurrent workers |
| `QQ_MAX_DEPTH` | 3 | Maximum sub-agent depth |
| `QQ_CHILD_TIMEOUT` | 300 | Per-task timeout (seconds) |

**Update CLAUDE.md**:

```markdown
Child process / recursive calling:
- `QQ_CHILD_TIMEOUT`: Timeout for child processes in seconds (default: 300)
- `QQ_MAX_PARALLEL`: Max concurrent child processes (default: 5)
- `QQ_MAX_DEPTH`: Max recursion depth (default: 3)
- `QQ_MAX_OUTPUT`: Max output size from children in chars (default: 50000)
- `QQ_MAX_QUEUED`: Max tasks in queue per agent (default: 10)  # NEW
```

---

## Usage Patterns

### Pattern 1: Simple Batch Processing

```python
# Agent processes 10 files
schedule_tasks('[
    {"task": "Summarize /docs/ch1.md"},
    {"task": "Summarize /docs/ch2.md"},
    {"task": "Summarize /docs/ch3.md"},
    {"task": "Summarize /docs/ch4.md"},
    {"task": "Summarize /docs/ch5.md"},
    {"task": "Summarize /docs/ch6.md"},
    {"task": "Summarize /docs/ch7.md"},
    {"task": "Summarize /docs/ch8.md"},
    {"task": "Summarize /docs/ch9.md"},
    {"task": "Summarize /docs/ch10.md"}
]')

# Execute all at once
execute_scheduled_tasks()
```

### Pattern 2: Hierarchical File Processing (100+ files)

```
Root Agent (depth 0):
├── schedule_tasks() with 10 directory processors
│
├── Child 1 (depth 1): Process /src/api/
│   └── schedule_tasks() with 10 file processors
│       ├── Grandchild 1.1: process api/users.py
│       ├── Grandchild 1.2: process api/auth.py
│       └── ... (8 more)
│
├── Child 2 (depth 1): Process /src/models/
│   └── schedule_tasks() with 10 file processors
│       └── ... (10 files)
│
└── ... (8 more directory processors)

RESULT: 100 files processed (10 dirs × 10 files)
```

### Pattern 3: Deep Hierarchical (1000 files)

```
Root (depth 0): 10 module coordinators
└── Each Child (depth 1): 10 directory processors
    └── Each Grandchild (depth 2): 10 file processors
        └── Terminal (depth 3): Process single file

10 × 10 × 10 = 1,000 files processed
```

---

## Scaling Analysis

### Current vs Proposed Capacity

| Metric | Current | Proposed |
|--------|---------|----------|
| Queue Size | None (direct exec) | 10 |
| Parallel Workers | 5 | 5 |
| Max Depth | 3 | 3 |
| **Max Leaf Tasks** | ~125 | **1,000** |

### Resource Considerations

**Memory**: Each queued task is lightweight (~1KB). 1000 tasks ≈ 1MB queue overhead.

**Processes**: Max concurrent at any time = `max_parallel` per active agent. With 10 agents active at depth 2 running parallel: 10 × 5 = 50 concurrent processes max.

**Time**: Assuming 30s per leaf task with 5 parallel workers:
- 1000 tasks / 5 parallel = 200 batches
- 200 × 30s = 6000s = 100 minutes theoretical minimum

---

## Testing Plan

### Unit Tests

**File**: `tests/test_task_queue.py`

```python
def test_queue_single_task():
    """Test queuing a single task."""
    queue = TaskQueue(mock_child_process, max_queued=10)
    task_id = queue.queue_task("test task")
    assert task_id.startswith("task_")
    assert queue.pending_count() == 1

def test_queue_full_error():
    """Test queue full rejection."""
    queue = TaskQueue(mock_child_process, max_queued=2)
    queue.queue_task("task 1")
    queue.queue_task("task 2")
    with pytest.raises(QueueFullError):
        queue.queue_task("task 3")

def test_priority_ordering():
    """Test tasks execute in priority order."""
    queue = TaskQueue(mock_child_process, max_queued=10, max_parallel=1)
    queue.queue_task("low", priority=0)
    queue.queue_task("high", priority=10)
    queue.queue_task("medium", priority=5)

    # Execute and verify order
    results = queue.execute_all()
    assert results[0].task == "high"
    assert results[1].task == "medium"
    assert results[2].task == "low"

def test_batch_queue():
    """Test batch queueing."""
    queue = TaskQueue(mock_child_process, max_queued=10)
    task_ids = queue.queue_batch([
        {"task": "task1"},
        {"task": "task2", "agent": "coder"},
        {"task": "task3", "priority": 5},
    ])
    assert len(task_ids) == 3
    assert queue.pending_count() == 3
```

### Integration Tests

```python
def test_hierarchical_execution():
    """Test multi-level task distribution."""
    # Simulate root queuing 3 tasks, each queuing 3 more
    # Total: 3 + 9 = 12 task executions
    pass

def test_depth_limit_with_queue():
    """Test queue respects depth limits."""
    os.environ["QQ_RECURSION_DEPTH"] = "3"
    cp = ChildProcess(max_depth=3)
    task_id = cp.queue_task("should fail")
    results = cp.execute_queue()
    assert not results[0].success
    assert "depth" in results[0].error.lower()
```

---

## Migration Path

### Backward Compatibility

Existing tools continue to work unchanged:
- `delegate_task()` - Single task delegation (immediate execution)
- `run_parallel_tasks()` - Batch parallel execution (immediate)

New tools are additive:
- `schedule_tasks()` - Queue tasks for later
- `execute_scheduled_tasks()` - Run queued tasks
- `get_queue_status()` - Inspect queue state

### Deprecation Plan

No deprecation needed. New queue-based tools complement existing immediate-execution tools.

---

## File Changes Summary

| File | Action | Description |
|------|--------|-------------|
| `src/qq/services/task_queue.py` | CREATE | TaskQueue class and QueueFullError |
| `src/qq/services/child_process.py` | MODIFY | Add queue integration |
| `src/qq/agents/__init__.py` | MODIFY | Add schedule_tasks, execute_scheduled_tasks, get_queue_status tools |
| `tests/test_task_queue.py` | CREATE | Unit tests |
| `docs/sub-agents.md` | MODIFY | Document new queue features |
| `CLAUDE.md` | MODIFY | Add QQ_MAX_QUEUED env var |

---

## Success Criteria

1. [ ] Can queue up to 10 tasks per agent
2. [ ] Queue enforces max_queued limit with clear error
3. [ ] Tasks execute in priority order
4. [ ] Hierarchical execution works: 10 × 10 × 10 = 1000 tasks
5. [ ] Existing delegate_task/run_parallel_tasks unchanged
6. [ ] Depth limit still enforced (depth 3 cannot spawn)
7. [ ] All existing tests pass
8. [ ] New tests cover queue functionality

---

## Open Questions

1. **Persistent queue?** Should queue survive agent restart? (Currently: No, in-memory only)
2. **Cross-agent queue sharing?** Should siblings share a queue? (Currently: No, per-agent)
3. **Streaming results?** Should results stream as tasks complete? (Currently: Batch return)
4. **Dynamic priority?** Should priority be adjustable after queuing? (Currently: No)

---

## References

- Current implementation: `src/qq/services/child_process.py`
- Existing tools: `src/qq/agents/__init__.py:184-247`
- User docs: `docs/sub-agents.md`
- Previous plan: `docs/plans/recursive-calling.md`
