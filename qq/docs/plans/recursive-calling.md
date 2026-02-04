# Recursive Calling Module for QQ

## Overview

This document outlines the implementation of a `ChildProcess` service module that enables QQ agents to spawn and coordinate new QQ instances as subprocesses. This allows the primary agent to delegate tasks to specialized child agents, enabling hierarchical problem decomposition and parallel task execution.

## Motivation

1. **Task Decomposition**: Complex tasks can be broken into subtasks handled by specialized agents
2. **Parallel Execution**: Multiple independent subtasks can run concurrently
3. **Agent Specialization**: Different agents (coder, researcher, etc.) can be invoked for domain-specific work
4. **Isolation**: Child instances have separate sessions, preventing state pollution
5. **Scalability**: Work distribution across multiple agent instances

## Current State Analysis

### Existing Infrastructure (Leverage These)

| Component | File | Relevance |
|-----------|------|-----------|
| Session System | `src/qq/session.py` | Child instances auto-generate unique sessions |
| CLI Mode | `src/qq/cli.py` | `-m` flag enables one-shot execution |
| Agent Loading | `src/qq/agents/__init__.py` | `--agent` flag selects different agents |
| FileManager Pattern | `src/qq/services/file_manager.py` | Service class pattern to follow |

### CLI Mode Already Supports

```bash
# One-shot execution (perfect for child processes)
./qq -m "Explain Python GIL"

# Agent selection
./qq --agent coder -m "Write a function to sort a list"

# New session (ensures isolation)
./qq --new-session -m "task"
```

---

## Design: ChildProcess Service

### Core Concept

A new service class `ChildProcess` that manages spawning QQ subprocesses, capturing their output, and returning results to the parent agent.

```
┌─────────────────────┐
│   Parent QQ Agent   │
│  (console/cli mode) │
└──────────┬──────────┘
           │ spawn_agent() / run_parallel()
           ▼
┌──────────────────────────────────────────┐
│           ChildProcess Service           │
│  - subprocess management                 │
│  - output capture                        │
│  - timeout handling                      │
│  - parallel execution                    │
└──────────────────────────────────────────┘
           │
    ┌──────┴──────┬──────────────┐
    ▼             ▼              ▼
┌────────┐  ┌────────┐     ┌────────┐
│ Child  │  │ Child  │     │ Child  │
│ QQ #1  │  │ QQ #2  │ ... │ QQ #N  │
│(coder) │  │(default)│    │(custom)│
└────────┘  └────────┘     └────────┘
```

### Directory Structure

```
src/qq/services/
├── __init__.py
├── file_manager.py      # Existing
├── graph.py             # Existing
└── child_process.py     # NEW - Child process management
```

---

## Implementation Plan

### Phase 1: Core ChildProcess Service

#### Task 1.1: Create ChildProcess Module

**File**: `src/qq/services/child_process.py`

```python
"""Child process management for recursive QQ invocation.

Enables parent QQ agents to spawn child QQ instances as subprocesses
for task delegation and parallel execution.
"""

import os
import sys
import subprocess
import json
import asyncio
from pathlib import Path
from typing import Optional, List, Dict, Any
from dataclasses import dataclass
from concurrent.futures import ThreadPoolExecutor, as_completed


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
        default_timeout: int = 300,
        max_parallel: int = 5,
    ):
        """Initialize ChildProcess manager.

        Args:
            qq_executable: Path to qq executable. Auto-detected if None.
            default_timeout: Default timeout in seconds for child processes.
            max_parallel: Maximum concurrent child processes.
        """
        self.qq_executable = qq_executable or self._find_qq_executable()
        self.default_timeout = default_timeout
        self.max_parallel = max_parallel

    def _find_qq_executable(self) -> str:
        """Find the qq executable path."""
        # Try common locations
        candidates = [
            Path(sys.executable).parent / "qq",  # Same venv
            Path.cwd() / "qq",                    # Project root
            "qq",                                  # PATH
        ]
        for candidate in candidates:
            if Path(candidate).exists() or shutil.which(str(candidate)):
                return str(candidate)
        # Fallback to module execution
        return f"{sys.executable} -m qq"

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
        timeout = timeout or self.default_timeout

        cmd = self._build_command(task, agent)

        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=timeout,
                cwd=working_dir,
                env=self._child_env(),
            )

            return ChildResult(
                success=result.returncode == 0,
                output=result.stdout.strip(),
                error=result.stderr.strip() if result.stderr else None,
                exit_code=result.returncode,
                agent=agent,
                task=task,
            )

        except subprocess.TimeoutExpired:
            return ChildResult(
                success=False,
                output="",
                error=f"Child process timed out after {timeout}s",
                exit_code=-1,
                agent=agent,
                task=task,
            )
        except Exception as e:
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
        results = [None] * len(tasks)

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
                    results[idx] = ChildResult(
                        success=False,
                        output="",
                        error=str(e),
                        agent=tasks[idx].get("agent", "default"),
                        task=tasks[idx]["task"],
                    )

        return results

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
        # Could add: QQ_PARENT_SESSION for tracing
        return env
```

---

### Phase 2: Tool Integration

#### Task 2.1: Create Tools Wrapper

**File**: `src/qq/agents/__init__.py` (modify)

Add child process tools alongside file manager tools:

```python
from qq.services.child_process import ChildProcess

def load_agent(name: str) -> Tuple[Agent, FileManager]:
    # ... existing code ...

    # Initialize ChildProcess service
    child_process = ChildProcess()

    @tool
    def delegate_task(task: str, agent: str = "default") -> str:
        """
        Delegate a task to a child QQ agent.

        Use this to break down complex tasks or leverage specialized agents.
        The child agent runs in isolation with its own session.

        Args:
            task: The task description or prompt for the child agent.
            agent: Which agent to use (default, coder, etc.).

        Returns:
            The child agent's response.
        """
        result = child_process.spawn_agent(task, agent)
        if result.success:
            return result.output
        else:
            return f"Child agent error: {result.error}"

    @tool
    def run_parallel_tasks(tasks_json: str) -> str:
        """
        Run multiple tasks in parallel using child QQ agents.

        Args:
            tasks_json: JSON array of task objects, each with:
                - task: The task description (required)
                - agent: Agent to use (optional, default: "default")

        Example:
            tasks_json = '[{"task": "Summarize file A"}, {"task": "Analyze file B", "agent": "coder"}]'

        Returns:
            JSON array of results.
        """
        try:
            tasks = json.loads(tasks_json)
            results = child_process.run_parallel(tasks)
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
        except json.JSONDecodeError as e:
            return f"Invalid JSON: {e}"

    agent_tools.extend([delegate_task, run_parallel_tasks])
```

---

### Phase 3: Safety and Limits

#### Task 3.1: Add Recursion Depth Tracking

Prevent infinite recursion by tracking depth via environment variable:

```python
# In ChildProcess._child_env()
def _child_env(self) -> Dict[str, str]:
    env = os.environ.copy()
    env.pop("QQ_SESSION_ID", None)

    # Track recursion depth
    current_depth = int(env.get("QQ_RECURSION_DEPTH", "0"))
    env["QQ_RECURSION_DEPTH"] = str(current_depth + 1)

    return env

# In ChildProcess.spawn_agent()
def spawn_agent(self, ...):
    # Check depth before spawning
    current_depth = int(os.environ.get("QQ_RECURSION_DEPTH", "0"))
    if current_depth >= self.max_depth:
        return ChildResult(
            success=False,
            output="",
            error=f"Maximum recursion depth ({self.max_depth}) exceeded",
            ...
        )
    # ... rest of method
```

#### Task 3.2: Add Resource Limits

```python
class ChildProcess:
    def __init__(
        self,
        ...
        max_depth: int = 3,           # Max recursion depth
        max_output_size: int = 50000, # Max output chars to capture
    ):
        self.max_depth = max_depth
        self.max_output_size = max_output_size

    def spawn_agent(self, ...):
        # ... subprocess.run() ...

        # Truncate large outputs
        output = result.stdout[:self.max_output_size]
        if len(result.stdout) > self.max_output_size:
            output += f"\n\n[Output truncated at {self.max_output_size} chars]"
```

---

### Phase 4: Observability

#### Task 4.1: Logging and Tracing

```python
import logging
from uuid import uuid4

logger = logging.getLogger("child_process")

class ChildProcess:
    def spawn_agent(self, ...):
        trace_id = uuid4().hex[:8]
        logger.info(f"[{trace_id}] Spawning child: agent={agent}, task={task[:50]}...")

        # ... run subprocess ...

        logger.info(f"[{trace_id}] Child completed: success={result.success}, exit={result.exit_code}")
        return result
```

#### Task 4.2: Parent Session Tracking (Optional)

```python
def _child_env(self) -> Dict[str, str]:
    env = os.environ.copy()

    # Pass parent session for tracing
    from qq.session import get_session_id
    env["QQ_PARENT_SESSION"] = get_session_id()

    return env
```

---

## Tool Descriptions for LLM

The tools should have clear docstrings so the LLM knows when to use them:

### `delegate_task`

```
Delegate a task to a specialized child QQ agent.

When to use:
- Complex tasks that benefit from focused attention
- Tasks requiring a specialized agent (coder, researcher)
- Subtasks that can be handled independently

Example: delegate_task("Write unit tests for the sort function", agent="coder")
```

### `run_parallel_tasks`

```
Execute multiple independent tasks concurrently.

When to use:
- Multiple files need similar processing
- Independent research queries
- Batch operations that don't depend on each other

Example: run_parallel_tasks('[
  {"task": "Summarize chapter 1"},
  {"task": "Summarize chapter 2"},
  {"task": "Summarize chapter 3"}
]')
```

---

## Verification Plan

### Manual Testing

1. **Basic Delegation**:
   ```bash
   ./qq -m "Use delegate_task to have the default agent explain recursion"
   ```

2. **Agent Selection**:
   ```bash
   ./qq -m "Delegate to the coder agent to write a fibonacci function"
   ```

3. **Parallel Execution**:
   ```bash
   ./qq -m "Run parallel tasks to summarize 3 different concepts: recursion, iteration, memoization"
   ```

4. **Recursion Limit**:
   ```bash
   # Should hit depth limit and return error
   ./qq -m "Use delegate_task to create a chain: have the child also delegate a task"
   ```

5. **Timeout Handling**:
   ```bash
   # Configure short timeout and give long task
   ./qq -m "Delegate a task that takes forever (test timeout)"
   ```

### Unit Tests

**File**: `tests/test_child_process.py`

```python
import pytest
from qq.services.child_process import ChildProcess, ChildResult

def test_spawn_agent_success():
    cp = ChildProcess(timeout=30)
    result = cp.spawn_agent("What is 2+2?", agent="default")
    assert result.success
    assert result.output  # Has some output

def test_spawn_agent_timeout():
    cp = ChildProcess(default_timeout=1)  # 1 second
    result = cp.spawn_agent("Count to infinity")
    assert not result.success
    assert "timeout" in result.error.lower()

def test_recursion_depth_limit():
    os.environ["QQ_RECURSION_DEPTH"] = "3"
    cp = ChildProcess(max_depth=3)
    result = cp.spawn_agent("Any task")
    assert not result.success
    assert "depth" in result.error.lower()
    del os.environ["QQ_RECURSION_DEPTH"]

def test_run_parallel():
    cp = ChildProcess()
    tasks = [
        {"task": "What is 1+1?"},
        {"task": "What is 2+2?"},
    ]
    results = cp.run_parallel(tasks)
    assert len(results) == 2
    assert all(r.success for r in results)
```

---

## File Changes Summary

| File | Action | Description |
|------|--------|-------------|
| `src/qq/services/child_process.py` | CREATE | New service module |
| `src/qq/agents/__init__.py` | MODIFY | Add delegate_task, run_parallel_tasks tools |
| `tests/test_child_process.py` | CREATE | Unit tests |

---

## Configuration Options

### Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `QQ_CHILD_TIMEOUT` | 300 | Default timeout (seconds) |
| `QQ_MAX_PARALLEL` | 5 | Max concurrent children |
| `QQ_MAX_DEPTH` | 3 | Max recursion depth |
| `QQ_RECURSION_DEPTH` | 0 | Current depth (internal) |
| `QQ_PARENT_SESSION` | None | Parent session ID (tracing) |

---

## Future Enhancements

### Phase 5 (Future): Streaming Output

```python
async def spawn_agent_streaming(self, task: str, agent: str) -> AsyncIterator[str]:
    """Stream child agent output as it's generated."""
    # Use asyncio subprocess with stdout streaming
    pass
```

### Phase 6 (Future): Result Caching

```python
class ChildProcess:
    def __init__(self, ..., cache_results: bool = True):
        self.cache = {}  # task_hash -> result

    def spawn_agent(self, task: str, ...):
        cache_key = hash((task, agent))
        if cache_key in self.cache:
            return self.cache[cache_key]
        # ... run subprocess ...
        self.cache[cache_key] = result
        return result
```

### Phase 7 (Future): Inter-Agent Communication

```python
# Allow child to send messages back to parent during execution
# via named pipes or shared memory
```

---

## Implementation Order

1. **Phase 1**: Core ChildProcess service (foundation)
2. **Phase 2**: Tool integration into agents
3. **Phase 3**: Safety limits (recursion, resources)
4. **Phase 4**: Logging and observability
5. **Testing**: Manual + unit tests

---

## Success Criteria

1. Parent agent can delegate tasks to child agents via tool call
2. Child agents run in isolated sessions (no state pollution)
3. Parallel execution works for multiple independent tasks
4. Recursion depth is enforced to prevent infinite loops
5. Timeouts prevent hung child processes
6. Output is captured and returned cleanly
7. Different agent types can be invoked (default, coder, etc.)
8. All existing tests continue to pass
