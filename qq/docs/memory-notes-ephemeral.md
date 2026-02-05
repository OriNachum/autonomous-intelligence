# Ephemeral Notes

Ephemeral notes provide isolated working memory for sub-agents, allowing each child process to maintain its own context without affecting the main notes file.

## Overview

| Property | Value |
|----------|-------|
| **Manager** | `NotesManager` |
| **Source** | `src/qq/memory/notes.py` |
| **Storage** | File (`memory/notes.{notes_id}.md`) |
| **Lock File** | `memory/notes.{notes_id}.lock` |

## Purpose

Ephemeral notes enable:
- **Session isolation**: Each sub-agent has private working memory
- **Parallel execution**: Multiple agents can run without conflicts
- **Task context**: Sub-agents receive focused context for their task
- **Automatic cleanup**: Notes can be deleted when task completes

## File Naming

| Agent Type | Notes File |
|------------|------------|
| Root/Main agent | `notes.md` |
| Sub-agent (task_0001) | `notes.task_0001.md` |
| Sub-agent (task_0002) | `notes.task_0002.md` |

## Environment Variable

The `QQ_NOTES_ID` environment variable determines which notes file to use:

```bash
# Main agent (no notes_id)
./qq -m "Hello"

# Sub-agent with specific notes_id
QQ_NOTES_ID=task_0001 ./qq -m "Research Python"
```

## API Reference

### Getting the Correct Manager

```python
from qq.memory.notes import get_notes_manager

# Automatically uses QQ_NOTES_ID if set
manager = get_notes_manager()
```

### Creating Ephemeral Notes

Parent agents can create ephemeral notes for children:

```python
from qq.memory.notes import NotesManager

# Create new ephemeral notes with initial context
manager = NotesManager.create_ephemeral(
    notes_id="task_0001",
    initial_context="Research Python web frameworks for the project",
    memory_dir="./memory"
)
```

This creates:
```markdown
# QQ Agent Notes (task_0001)

Last updated: 2026-02-05 14:30

## Task Context
Research Python web frameworks for the project

## Key Topics

## Important Facts

## Ongoing Threads

## File Knowledge
```

### Cleanup

```python
# Remove ephemeral notes when done
success = manager.cleanup()  # Returns True if removed
```

**Note**: Cleanup only works for ephemeral notes (`is_ephemeral=True`).

## NotesManager Properties

| Property | Description |
|----------|-------------|
| `notes_id` | The identifier (None for main agent) |
| `notes_file` | Path to the notes file |
| `lock_file` | Path to the lock file |
| `is_ephemeral` | True if this is an ephemeral notes file |

## File Sections

Ephemeral notes have the same sections as main notes:

| Section | Purpose |
|---------|---------|
| `Task Context` | Initial context from parent (ephemeral only) |
| `Key Topics` | Main topics for this task |
| `Important Facts` | Relevant facts discovered |
| `Ongoing Threads` | Active sub-tasks |
| `File Knowledge` | Files read/analyzed |

## Concurrency Safety

Like main notes, ephemeral notes use file locking:

- Each ephemeral file has its own lock file
- Atomic writes via temp file + rename
- Safe for parallel access (though typically single-agent)

## Integration with Sub-Agents

When spawning a sub-agent via `child_process.py`:

1. Parent generates unique `notes_id` (e.g., `task_{timestamp}_{random}`)
2. Parent creates ephemeral notes with task context
3. Parent sets `QQ_NOTES_ID` environment variable
4. Child agent uses its isolated notes file
5. On completion, parent can read results and cleanup

```python
# In child_process.py
import os
from qq.memory.notes import NotesManager

# Create ephemeral notes for child
notes_id = f"task_{int(time.time())}_{random.randint(1000, 9999)}"
NotesManager.create_ephemeral(
    notes_id=notes_id,
    initial_context=task_description,
)

# Set environment for child process
env = os.environ.copy()
env["QQ_NOTES_ID"] = notes_id

# Spawn child...
```

## Difference from Main Notes

| Aspect | Main Notes | Ephemeral Notes |
|--------|------------|-----------------|
| File | `notes.md` | `notes.{id}.md` |
| Scope | All sessions | Single sub-agent |
| Persistence | Permanent | Until cleanup |
| Initial content | Template | Task context |
| Cleanup | Manual | Automatic option |
| MongoDB sync | Yes | Optional |

## Best Practices

1. **Always set context**: Create ephemeral notes with relevant task context
2. **Cleanup after use**: Remove ephemeral files when task completes
3. **Unique IDs**: Use timestamps + random to avoid collisions
4. **Don't share**: Each sub-agent should have its own notes_id

## Related Documentation

- [Memory Overview](./memory.md)
- [Core Notes](./memory-notes-core.md)
- [Flat Notes (MongoDB)](./memory-flat.md)
- [Sub-agents](./sub-agents.md)
