# Task Queue

The task queue provides bounded, priority-based scheduling for sub-agent work. It sits between the agent tool layer and the child process spawner, allowing agents to batch up tasks and execute them efficiently rather than spawning children one at a time.

## Why a Queue

Without the queue, agents must either delegate tasks one by one (`delegate_task`) or fire them all at once (`run_parallel_tasks`). Both approaches break down at scale:

- **One at a time** is slow for large batches
- **All at once** is limited to `QQ_MAX_PARALLEL` concurrent workers and provides no ordering control

The task queue adds a middle layer: accumulate work first, then execute it in priority order with bounded concurrency.

## Architecture

```
Agent Tool Layer (agents/__init__.py)
│
│  schedule_tasks()          ── queue tasks
│  execute_scheduled_tasks() ── drain and run
│  get_queue_status()        ── inspect state
│
▼
ChildProcess (services/child_process.py)
│
│  task_queue property (lazy init)
│  queue_task() / queue_batch()
│  execute_queue()
│
▼
TaskQueue (services/task_queue.py)
│
│  Bounded list of QueuedTask objects
│  Priority sorting before execution
│  ThreadPoolExecutor for concurrent spawn
│
▼
subprocess.run("./qq --agent X --new-session -m <task>")
```

### Key Classes

**`TaskQueue`** (`src/qq/services/task_queue.py`) — the core scheduler.

- Holds a bounded list of `QueuedTask` objects protected by a `threading.Lock`
- On `execute_all()`, sorts by priority (descending) then dispatches through a `ThreadPoolExecutor`
- Tracks each task through `TaskStatus`: PENDING → RUNNING → COMPLETED / FAILED / CANCELLED

**`QueuedTask`** — dataclass representing one queued item:

| Field | Type | Description |
|-------|------|-------------|
| `task_id` | str | Auto-generated (`task_0001`, `task_0002`, ...) |
| `task` | str | The prompt sent to the child agent |
| `agent` | str | Which agent to use (default: `"default"`) |
| `priority` | int | Higher numbers run first (default: `0`) |
| `context` | str | Optional initial context for ephemeral notes |
| `status` | TaskStatus | Current lifecycle state |
| `result` | ChildResult | Populated after execution |
| `metadata` | dict | Arbitrary user-attached data |

**`QueueFullError`** — raised when `queue_task` is called and the queue is at `max_queued` capacity.

## Lifecycle

```
1. queue_task() / queue_batch()
   └─ Validates capacity (raises QueueFullError if full)
   └─ Assigns task_id, sets status=PENDING
   └─ Appends to _pending list

2. execute_all()
   └─ Copies and clears _pending (under lock)
   └─ Sorts by priority (highest first)
   └─ Submits to ThreadPoolExecutor (max_parallel workers)
   └─ Updates status: PENDING → RUNNING → COMPLETED/FAILED
   └─ Returns List[ChildResult] in priority order

3. clear()
   └─ Cancels all pending tasks (status → CANCELLED)
   └─ Returns count of cancelled tasks
```

## Integration with ChildProcess

`TaskQueue` does not spawn processes directly. It delegates to `ChildProcess.spawn_agent()` for each task, which handles:

- Recursion depth checking (`QQ_RECURSION_DEPTH`)
- Ephemeral notes creation and cleanup
- Subprocess invocation with `--new-session` isolation
- Output capture and truncation
- Timeout enforcement

The `ChildProcess` class owns the queue via a lazy property:

```python
@property
def task_queue(self) -> TaskQueue:
    if self._task_queue is None:
        self._task_queue = TaskQueue(
            child_process=self,
            max_queued=self.max_queued,
            max_parallel=self.max_parallel,
        )
    return self._task_queue
```

This means the queue is only created when first needed, and inherits its limits from the `ChildProcess` configuration.

## Agent-Facing Tools

Three tools are exposed to agents (defined in `src/qq/agents/__init__.py`):

### `schedule_tasks(tasks_json)`

Queue tasks without executing them. Accepts a JSON array:

```json
[
  {"task": "Process batch A", "agent": "default", "priority": 10, "context": "Batch 1 of 5"},
  {"task": "Process batch B", "priority": 5},
  {"task": "Process batch C"}
]
```

Returns a JSON object with `queued` count, `task_ids`, and `pending` count.

### `execute_scheduled_tasks()`

Drains the queue and blocks until all tasks complete. Returns a JSON array of results (same format as `run_parallel_tasks`). Each result's output is summarized if it exceeds the summarization threshold.

### `get_queue_status()`

Returns queue state without modifying it:

```json
{
  "pending": 5,
  "max_queued": 10,
  "max_parallel": 5,
  "current_depth": 1,
  "max_depth": 3,
  "can_spawn": true
}
```

The `can_spawn` field is the primary check agents should use before scheduling work.

## Priority Execution

Tasks with higher `priority` values execute first. When `execute_all()` is called, the pending list is sorted descending by priority before submission to the thread pool.

With `max_parallel=1`, execution order is strictly by priority. With higher parallelism, the first `max_parallel` tasks start concurrently (still the highest-priority ones), with remaining tasks starting as workers become free.

Default priority is `0`. Use higher values for time-sensitive or dependency-critical work.

## Capacity and Limits

| Variable | Default | Description |
|----------|---------|-------------|
| `QQ_MAX_QUEUED` | 10 | Maximum pending tasks per queue |
| `QQ_MAX_PARALLEL` | 5 | Concurrent workers in the thread pool |

These limits are per agent instance. When combined with recursion depth, the system supports hierarchical fan-out:

```
Depth 0 (root):     10 queued tasks
Depth 1 (children): each can queue 10 more → 100 tasks
Depth 2 (leaves):   each can queue 10 more → 1,000 tasks
```

The total processing capacity is `max_queued ^ max_depth` (default: 10^3 = 1,000).

## Thread Safety

All queue mutations (`queue_task`, `queue_batch`, `execute_all`, `clear`, `pending_count`) are protected by a `threading.Lock`. The queue is safe to use from multiple threads, though typical usage is single-threaded within one agent's tool calls.

## Error Handling

- **Queue full**: `QueueFullError` with message including the capacity limit
- **Spawn failure**: Exception is caught, task status set to FAILED, `ChildResult` with `success=False` and the error message is returned in the results list
- **Timeout**: Handled by `ChildProcess.spawn_agent()`, returns a failed `ChildResult`
- **Partial batch failure**: If `queue_batch` exceeds capacity mid-batch, tasks queued before the overflow remain in the queue; the `QueueFullError` is raised for the task that exceeds the limit

## Relationship to Immediate Execution

The queue is an alternative to `run_parallel_tasks`, not a replacement. Use the appropriate tool based on the situation:

| Scenario | Tool | Why |
|----------|------|-----|
| 1-10 independent tasks | `run_parallel_tasks` | Simple, no scheduling overhead |
| 10+ tasks needing ordering | `schedule_tasks` + `execute_scheduled_tasks` | Priority control, bounded queue |
| Single focused task | `delegate_task` | Direct, no batching needed |
| Check before delegating | `get_queue_status` | Verify depth/capacity |

## Source Files

| File | Role |
|------|------|
| `src/qq/services/task_queue.py` | TaskQueue, QueuedTask, TaskStatus, QueueFullError |
| `src/qq/services/child_process.py` | ChildProcess with queue integration |
| `src/qq/agents/__init__.py` | Agent tool wrappers (schedule_tasks, etc.) |
| `tests/test_task_queue.py` | Test suite |
| `src/qq/agents/_shared/delegation.md` | Delegation strategy reference for agents |
