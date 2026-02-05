# Core Notes

Core notes contain protected, essential information that persists indefinitely and is never automatically forgotten.

## Overview

| Property | Value |
|----------|-------|
| **Manager** | `CoreNotesManager` |
| **Source** | `src/qq/memory/core_notes.py` |
| **Storage** | File (`memory/core.md`) |
| **Lock File** | `memory/core.lock` |

## Purpose

Core notes store crucial information that should never be lost:
- **User identity**: Name, location, role, preferences
- **Project identities**: Active projects being worked on
- **Key relationships**: Important people, collaborators
- **System configuration**: Hardware, setup details

## Protected Categories

| Category | Description | Examples |
|----------|-------------|----------|
| `Identity` | User's personal information | Name, location, role, email |
| `Projects` | Active projects | Project names, goals, tech stack |
| `Relationships` | Important people | Collaborators, team members |
| `System` | Hardware/setup details | GPU, server specs, tools |

## File Structure

```markdown
# Core Memory

Last updated: 2026-02-05 14:30

These are protected notes that will never be automatically forgotten.

## Identity
<!-- User's personal information: name, location, role, preferences -->
- User's name is Alex
- Works as a software engineer
- Located in San Francisco

## Projects
<!-- Active projects the user is working on -->
- Building QQ conversational AI agent
- Working on knowledge graph enhancement

## Relationships
<!-- Important people, collaborators, contacts -->
- Collaborates with Sarah on ML projects
- Reports to Mike (engineering manager)

## System
<!-- Hardware, setup, configuration details -->
- Primary machine: RTX 4090, 64GB RAM
- Uses VS Code with vim keybindings
```

## Automatic Detection

The system can detect content that should be core notes based on patterns:

### Identity Patterns
- "my name", "I am", "I'm", "I prefer", "call me"
- "my role", "I work", "my job", "I do"
- "I live", "my location", "I'm from", "I'm in"
- "my email", "my phone", "contact me"

### Project Patterns
- "my project", "I'm building/working on/developing"
- "our project/system/app"

### Relationship Patterns
- "collaborat", "colleague", "team", "partner", "friend"

### System Patterns
- "hardware", "gpu", "cpu", "server", "machine", "setup", "config"

## API Reference

### CoreNotesManager

```python
from qq.memory.core_notes import CoreNotesManager

manager = CoreNotesManager(memory_dir="./memory")
```

| Method | Description |
|--------|-------------|
| `load_notes()` | Load or create core notes file |
| `get_notes()` | Get current content |
| `add_core(content, category, source)` | Add item to category |
| `remove_core(pattern, category)` | Remove matching items |
| `get_items_by_category(category)` | Get items in category |
| `get_all_items()` | Get all items organized by category |
| `is_protected(content)` | Check if content is protected |

### Adding Core Notes

```python
manager.add_core(
    content="User's name is Alex",
    category="Identity",
    source="auto"  # or "migration", "manual"
)
```

### Checking Protection

```python
if manager.is_protected("Alex"):
    print("This information is in core notes")
```

### Automatic Promotion

High-importance notes can be suggested for core promotion:

```python
category = manager.suggest_promotion(
    content="My GPU is RTX 4090",
    importance=0.9
)
# Returns: "System"
```

## Concurrency Safety

Core notes use file locking for safe parallel access:

```python
with manager._file_lock(exclusive=True):
    # Safe write operations
    pass

with manager._file_lock(exclusive=False):
    # Safe read operations
    pass
```

- **Exclusive lock**: For write operations
- **Shared lock**: For read operations
- **Atomic writes**: Uses temp file + rename pattern

## Difference from Regular Notes

| Aspect | Core Notes | Regular Notes |
|--------|------------|---------------|
| Storage | `core.md` file | `notes.md` + MongoDB |
| Forgetting | Never auto-forgotten | Can decay/archive |
| Categories | Fixed (4 protected) | Flexible sections |
| Purpose | Essential identity | General context |
| Scope | Shared across sessions | Can be ephemeral |

## Integration with NotesAgent

The NotesAgent checks for core note candidates:

1. Extracts new notes from conversation
2. Scores importance of each note
3. Checks if content matches core patterns
4. Suggests promotion for high-importance matches
5. User can approve promotion to core

## Related Documentation

- [Memory Overview](./memory.md)
- [Flat Notes (MongoDB)](./memory-flat.md)
- [Ephemeral Notes](./memory-notes-ephemeral.md)
