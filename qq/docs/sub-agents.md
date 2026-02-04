# Sub-Agents: Recursive and Parallel Execution

QQ supports spawning child agent instances to handle delegated tasks. This enables hierarchical problem decomposition, parallel execution, and leveraging specialized agents for specific subtasks.

## Overview

The sub-agent system allows a parent QQ agent to:

1. **Delegate tasks** to child agents running in isolated sessions
2. **Run tasks in parallel** for independent operations
3. **Leverage specialized agents** (e.g., coder, researcher) for domain-specific work
4. **Decompose complex problems** into manageable subtasks

```
┌─────────────────────────┐
│    Parent QQ Agent      │
│   (console/cli mode)    │
└───────────┬─────────────┘
            │ delegate_task() / run_parallel_tasks()
            ▼
┌─────────────────────────────────────────────────┐
│            ChildProcess Service                 │
│  • subprocess management                        │
│  • output capture                               │
│  • timeout handling                             │
│  • recursion depth tracking                     │
└─────────────────────────────────────────────────┘
            │
     ┌──────┴──────┬──────────────┐
     ▼             ▼              ▼
┌─────────┐  ┌─────────┐    ┌─────────┐
│ Child   │  │ Child   │    │ Child   │
│ QQ #1   │  │ QQ #2   │... │ QQ #N   │
│(default)│  │(coder)  │    │(custom) │
└─────────┘  └─────────┘    └─────────┘
```

## Tools

### `delegate_task`

Delegates a single task to a child QQ agent.

**Parameters:**
| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `task` | string | required | The task description or prompt |
| `agent` | string | "default" | Which agent to use |

**When to use:**
- Complex tasks that benefit from focused attention
- Tasks requiring a specialized agent
- Subtasks that can be handled independently

**Example:**
```
delegate_task("Write a Python function to calculate fibonacci numbers", agent="coder")
```

**Returns:** The child agent's response text, or an error message if the child failed.

---

### `run_parallel_tasks`

Executes multiple tasks concurrently using child QQ agents.

**Parameters:**
| Parameter | Type | Description |
|-----------|------|-------------|
| `tasks_json` | string | JSON array of task objects |

Each task object can have:
- `task` (required): The task description
- `agent` (optional): Agent to use (default: "default")

**When to use:**
- Multiple files need similar processing
- Independent research queries
- Batch operations that don't depend on each other

**Example:**
```json
[
  {"task": "Summarize chapter 1 of the document"},
  {"task": "Summarize chapter 2 of the document"},
  {"task": "Analyze the code in src/main.py", "agent": "coder"}
]
```

**Returns:** JSON array of results:
```json
[
  {
    "task": "Summarize chapter 1...",
    "agent": "default",
    "success": true,
    "output": "Chapter 1 discusses...",
    "error": null
  },
  ...
]
```

## How It Works

### Subprocess Execution

Each child agent runs as a separate QQ process:

```bash
./qq --agent <agent> --new-session -m "<task>"
```

Key aspects:
- **Session Isolation**: `--new-session` ensures each child has its own session, preventing state pollution
- **Output Capture**: stdout is captured and returned to the parent
- **Error Handling**: stderr and exit codes are tracked

### Recursion Depth Tracking

To prevent infinite recursion, QQ tracks depth via the `QQ_RECURSION_DEPTH` environment variable:

1. Parent starts at depth 0
2. Each child increments depth by 1
3. If depth reaches `QQ_MAX_DEPTH` (default 3), spawning fails

```
Parent (depth=0)
  └── Child A (depth=1)
        └── Child A1 (depth=2)
              └── Child A1a (depth=3) ✗ BLOCKED
```

### Parallel Execution

`run_parallel_tasks` uses a thread pool to spawn children concurrently:

- Default max workers: 5 (`QQ_MAX_PARALLEL`)
- Results are returned in input order, not completion order
- Each task runs independently with its own timeout

## Configuration

### Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `QQ_CHILD_TIMEOUT` | 300 | Timeout per child process (seconds) |
| `QQ_MAX_PARALLEL` | 5 | Maximum concurrent child processes |
| `QQ_MAX_DEPTH` | 3 | Maximum recursion depth |
| `QQ_MAX_OUTPUT` | 50000 | Maximum output size (characters) |

### Setting Configuration

```bash
# In your shell or .env file
export QQ_CHILD_TIMEOUT=600      # 10 minute timeout
export QQ_MAX_PARALLEL=10        # Allow 10 concurrent children
export QQ_MAX_DEPTH=5            # Allow deeper recursion
```

## Safety Features

### Recursion Limits

Prevents runaway recursive calls that could exhaust resources:
```
Error: Maximum recursion depth (3) exceeded
```

### Timeouts

Each child process has a configurable timeout. If exceeded:
```
Child agent error: Child process timed out after 300s
```

### Output Truncation

Large outputs are truncated to prevent memory issues:
```
[Output truncated at 50000 chars]
```

### Session Isolation

Each child runs with `--new-session`, ensuring:
- Separate conversation history
- Independent file manager state
- No cross-contamination between tasks

## Use Cases

### 1. Task Decomposition

Break a complex task into subtasks:

```
User: "Analyze this codebase and create documentation"

Agent thinking:
1. delegate_task("List all Python files and their purposes", agent="default")
2. delegate_task("Document the API endpoints", agent="coder")
3. delegate_task("Create a README with setup instructions", agent="default")
```

### 2. Parallel Research

Gather information from multiple sources simultaneously:

```
run_parallel_tasks('[
  {"task": "What are the key features of React 19?"},
  {"task": "What are the key features of Vue 4?"},
  {"task": "What are the key features of Angular 18?"}
]')
```

### 3. Batch File Processing

Process multiple files with the same operation:

```
run_parallel_tasks('[
  {"task": "Summarize the file at /docs/chapter1.md"},
  {"task": "Summarize the file at /docs/chapter2.md"},
  {"task": "Summarize the file at /docs/chapter3.md"}
]')
```

### 4. Specialized Agent Delegation

Use domain-specific agents for appropriate tasks:

```
delegate_task("Review this code for security vulnerabilities", agent="security")
delegate_task("Optimize this SQL query", agent="database")
delegate_task("Write unit tests for this function", agent="coder")
```

## Architecture

### Source Files

| File | Description |
|------|-------------|
| `src/qq/services/child_process.py` | Core ChildProcess service |
| `src/qq/agents/__init__.py` | Tool integration (delegate_task, run_parallel_tasks) |

### Classes

**`ChildProcess`**: Manages spawning and coordinating child processes
- `spawn_agent(task, agent, timeout, working_dir)` → `ChildResult`
- `run_parallel(tasks, timeout)` → `List[ChildResult]`

**`ChildResult`**: Dataclass for subprocess results
- `success: bool`
- `output: str`
- `error: Optional[str]`
- `exit_code: int`
- `agent: str`
- `task: str`

## Logging

Child process operations are logged to `logs/child_process.log`:

```
2024-02-04 10:30:15 - child_process - INFO - [a1b2c3d4] Spawning child: agent=coder, depth=1, task=Write a function...
2024-02-04 10:30:45 - child_process - INFO - [a1b2c3d4] Child completed: success=True, exit=0
```

## Limitations

1. **No streaming**: Child output is returned only after completion
2. **No inter-agent communication**: Children cannot send messages back during execution
3. **Memory isolation**: Children don't share memory/context with parent
4. **Resource consumption**: Each child is a full QQ process

## Future Enhancements

Planned improvements (see `docs/plans/recursive-calling.md`):

- **Streaming output**: Real-time output from children
- **Result caching**: Cache identical task results
- **Inter-agent messaging**: Allow children to communicate with parent during execution
- **Resource pooling**: Reuse child processes for multiple tasks
