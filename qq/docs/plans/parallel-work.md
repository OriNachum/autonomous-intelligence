# Parallel Execution Support for QQ

## Overview

This document provides a comprehensive plan to ensure QQ can run multiple instances in parallel safely. The investigation identified critical race conditions in file-based state management that must be addressed.

## Current State Analysis

### Critical Issues (MUST FIX)

| Component | File | Issue | Severity |
|-----------|------|-------|----------|
| History | `~/.qq/<agent>/history.json` | No locking, last write wins | CRITICAL |
| Notes | `./memory/notes.md` | TOCTOU race in all operations | CRITICAL |
| File Reads Registry | `_pending_file_reads` global | Module-level list collision | HIGH |
| File Manager State | `~/.qq/<agent>/files_state.json` | Shared CWD state | HIGH |
| Default Agent Creation | `default.system.md` | Write race on first run | MEDIUM |

### Safe Components (No Changes Needed)

| Component | Reason |
|-----------|--------|
| MongoDB (MongoNotesStore) | Atomic upsert operations |
| Neo4j (Neo4jClient) | MERGE operations are idempotent |
| Skills Loading | Read-only after initialization |
| Console UI | Per-instance, no shared state |

---

## Design: Session-Based State Isolation

### Core Concept

Each QQ instance runs with a unique **session ID**. All mutable state is namespaced by session, eliminating file conflicts entirely.

```
~/.qq/
├── <agent_name>/
│   ├── sessions/
│   │   ├── <session_id_1>/
│   │   │   ├── history.json      # Per-session history
│   │   │   └── files_state.json  # Per-session file manager state
│   │   ├── <session_id_2>/
│   │   │   ├── history.json
│   │   │   └── files_state.json
│   │   └── ...
│   └── default.system.md         # Shared agent config (read-only after init)
```

### Session ID Generation

```python
# src/qq/session.py (NEW FILE)
import uuid
from datetime import datetime

def generate_session_id() -> str:
    """Generate unique session ID for this QQ instance."""
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    short_uuid = uuid.uuid4().hex[:8]
    return f"{timestamp}_{short_uuid}"
```

---

## Implementation Plan

### Phase 1: Session Infrastructure

#### Task 1.1: Create Session Module

**File**: `src/qq/session.py` (NEW)

```python
"""Session management for parallel QQ execution."""
import uuid
from datetime import datetime
from pathlib import Path
from typing import Optional

_current_session_id: Optional[str] = None

def generate_session_id() -> str:
    """Generate unique session ID."""
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    short_uuid = uuid.uuid4().hex[:8]
    return f"{timestamp}_{short_uuid}"

def get_session_id() -> str:
    """Get current session ID, generating if needed."""
    global _current_session_id
    if _current_session_id is None:
        _current_session_id = generate_session_id()
    return _current_session_id

def set_session_id(session_id: str) -> None:
    """Set session ID (for resuming sessions)."""
    global _current_session_id
    _current_session_id = session_id

def get_session_dir(base_dir: Path, agent_name: str) -> Path:
    """Get session-specific directory."""
    session_dir = base_dir / agent_name / "sessions" / get_session_id()
    session_dir.mkdir(parents=True, exist_ok=True)
    return session_dir
```

#### Task 1.2: Update CLI for Session Support

**File**: `src/qq/cli.py`

Add CLI arguments:
```python
parser.add_argument("--session", "-s", help="Session ID (for resuming)")
parser.add_argument("--new-session", action="store_true", help="Force new session")
```

---

### Phase 2: History Isolation

#### Task 2.1: Refactor History Class

**File**: `src/qq/history.py`

**Current** (race-prone):
```python
def __init__(self, agent_name: str):
    self.history_dir = Path(os.environ.get("HISTORY_DIR", "~/.qq")).expanduser() / agent_name
    self.history_file = self.history_dir / "history.json"
```

**New** (session-isolated):
```python
from qq.session import get_session_dir

def __init__(self, agent_name: str, session_id: Optional[str] = None):
    base_dir = Path(os.environ.get("HISTORY_DIR", "~/.qq")).expanduser()
    self.session_dir = get_session_dir(base_dir, agent_name)
    self.history_file = self.session_dir / "history.json"
```

#### Task 2.2: Add Atomic Writes

Even with session isolation, add atomic writes for crash safety:

```python
import tempfile
import os

def _save(self) -> None:
    """Save history atomically."""
    # Write to temp file first
    fd, tmp_path = tempfile.mkstemp(
        dir=self.session_dir,
        suffix=".json.tmp"
    )
    try:
        with os.fdopen(fd, 'w') as f:
            json.dump({"messages": self.messages}, f, indent=2)
        # Atomic rename
        os.replace(tmp_path, self.history_file)
    except:
        os.unlink(tmp_path)
        raise
```

---

### Phase 3: File Manager Isolation

#### Task 3.1: Remove Global State

**File**: `src/qq/services/file_manager.py`

**Current** (module-level global):
```python
_pending_file_reads: List[Dict[str, str]] = []

def get_pending_file_reads() -> List[Dict[str, str]]:
    return _pending_file_reads

def clear_pending_file_reads() -> None:
    global _pending_file_reads
    _pending_file_reads = []
```

**New** (instance-level):
```python
class FileManager:
    def __init__(self, state_dir: Path):
        self.state_dir = state_dir
        self.state_file = self.state_dir / "files_state.json"
        self.pending_file_reads: List[Dict[str, str]] = []  # Instance variable
        # ...

    def get_pending_file_reads(self) -> List[Dict[str, str]]:
        return self.pending_file_reads

    def clear_pending_file_reads(self) -> None:
        self.pending_file_reads = []
```

#### Task 3.2: Update FileManager State Directory

**File**: `src/qq/services/file_manager.py`

Update to use session directory:

```python
from qq.session import get_session_dir

class FileManager:
    def __init__(self, base_dir: Path, agent_name: str):
        self.state_dir = get_session_dir(base_dir, agent_name)
        self.state_file = self.state_dir / "files_state.json"
```

#### Task 3.3: Update Agent Loader

**File**: `src/qq/agents/__init__.py`

Update `load_agent()` to pass session-aware state:

```python
from qq.session import get_session_dir

def load_agent(name: str = "default", ...):
    base_dir = Path.home() / ".qq"
    session_dir = get_session_dir(base_dir, name)
    file_manager = FileManager(session_dir)
```

---

### Phase 4: Notes File Safety

#### Task 4.1: Add File Locking to Notes

**File**: `src/qq/memory/notes.py`

Add fcntl-based locking for Unix systems:

```python
import fcntl
from contextlib import contextmanager

@contextmanager
def _file_lock(self, exclusive: bool = True):
    """Acquire file lock for notes operations."""
    lock_file = self.notes_file.with_suffix(".lock")
    lock_file.touch(exist_ok=True)

    with open(lock_file, 'r') as f:
        try:
            fcntl.flock(f.fileno(),
                       fcntl.LOCK_EX if exclusive else fcntl.LOCK_SH)
            yield
        finally:
            fcntl.flock(f.fileno(), fcntl.LOCK_UN)

def _save(self) -> None:
    """Save notes with file locking."""
    with self._file_lock():
        # ... existing save logic
```

#### Task 4.2: Atomic Notes Updates

```python
def _save(self) -> None:
    """Save notes atomically with locking."""
    with self._file_lock():
        # Write to temp file
        tmp_path = self.notes_file.with_suffix(".md.tmp")
        # ... update timestamp and write
        tmp_path.write_text(self._content)
        # Atomic rename
        tmp_path.replace(self.notes_file)
```

---

### Phase 5: Default Agent Creation Safety

#### Task 5.1: Atomic Default Agent Creation

**File**: `src/qq/agents/__init__.py`

**Current** (race-prone):
```python
if not system_file.exists():
    system_file.write_text(system_prompt)
```

**New** (atomic):
```python
import tempfile
import os

def _create_default_agent_safely(agent_dir: Path, system_prompt: str) -> None:
    """Create default agent atomically."""
    system_file = agent_dir / "default.system.md"

    if system_file.exists():
        return

    agent_dir.mkdir(parents=True, exist_ok=True)

    # Atomic create: write to temp, then rename
    fd, tmp_path = tempfile.mkstemp(
        dir=agent_dir,
        suffix=".system.md.tmp"
    )
    try:
        with os.fdopen(fd, 'w') as f:
            f.write(system_prompt)
        # Atomic rename - fails if target exists (race safe)
        os.link(tmp_path, system_file)
        os.unlink(tmp_path)
    except FileExistsError:
        # Another instance created it first - that's fine
        os.unlink(tmp_path)
    except:
        os.unlink(tmp_path)
        raise
```

---

### Phase 6: App.py Thread Safety

#### Task 6.1: Remove Daemon Thread for Embeddings

**File**: `src/qq/app.py`

**Current** (thread-unsafe):
```python
embeddings_thread = threading.Thread(target=preload_embeddings, daemon=True)
embeddings_thread.start()
```

**Option A**: Remove preloading entirely (simplest)
```python
# Just create embeddings client when needed
shared_embeddings = EmbeddingClient()
```

**Option B**: Use threading.Lock for shared access
```python
_embeddings_lock = threading.Lock()

def get_embeddings() -> EmbeddingClient:
    with _embeddings_lock:
        # ... thread-safe access
```

#### Task 6.2: Move File Reads to FileManager Instance

**File**: `src/qq/app.py`

Update `_capture_file_reads_to_history()` to use FileManager instance:

```python
def _capture_file_reads_to_history(file_manager: FileManager, history: History) -> None:
    """Capture pending file reads to history."""
    pending = file_manager.get_pending_file_reads()
    # ... rest of logic
    file_manager.clear_pending_file_reads()
```

---

## Migration Guide

### Backward Compatibility

1. **Existing History**:
   - First run in parallel mode: copy `history.json` to `sessions/<new_session>/history.json`
   - Or start fresh with `--new-session`

2. **Environment Variables**:
   - No changes to `HISTORY_DIR`, `MEMORY_DIR` etc.
   - New optional: `QQ_SESSION_ID` to set session from environment

### Breaking Changes

1. `get_pending_file_reads()` now requires FileManager instance
2. History constructor now takes optional `session_id`
3. FileManager constructor signature changed

---

## Testing Plan

### Unit Tests

1. **Session Module**:
   - Test session ID generation uniqueness
   - Test session directory creation
   - Test session ID persistence

2. **History**:
   - Test session-isolated history files
   - Test atomic write crash recovery
   - Test concurrent writes don't corrupt

3. **FileManager**:
   - Test instance-level file reads list
   - Test session-isolated state files

4. **Notes**:
   - Test file locking prevents corruption
   - Test atomic saves

### Integration Tests

1. **Parallel Execution**:
   ```bash
   # Run 3 instances in parallel
   ./qq -m "test 1" &
   ./qq -m "test 2" &
   ./qq -m "test 3" &
   wait
   # Verify no corruption in any session
   ```

2. **Session Resume**:
   ```bash
   # Start session
   ./qq -m "remember this"
   # Note session ID from output
   # Resume later
   ./qq --session <id> -m "what did I say?"
   ```

---

## File Changes Summary

| File | Action | Changes |
|------|--------|---------|
| `src/qq/session.py` | CREATE | New session management module |
| `src/qq/cli.py` | MODIFY | Add --session, --new-session args |
| `src/qq/history.py` | MODIFY | Session-isolated paths, atomic writes |
| `src/qq/services/file_manager.py` | MODIFY | Instance-level state, remove globals |
| `src/qq/memory/notes.py` | MODIFY | File locking, atomic saves |
| `src/qq/agents/__init__.py` | MODIFY | Atomic default agent creation, session dirs |
| `src/qq/app.py` | MODIFY | Remove daemon thread, use FM instance |

---

## Implementation Order

1. **Phase 1**: Session infrastructure (foundation)
2. **Phase 2**: History isolation (most critical)
3. **Phase 3**: File manager isolation (second most critical)
4. **Phase 4**: Notes file safety (shared resource)
5. **Phase 5**: Default agent creation (edge case)
6. **Phase 6**: App.py thread safety (cleanup)

---

## Alternative Approaches Considered

### A. Database-Backed Everything

Move all state to MongoDB:
- History as MongoDB collection
- Notes as MongoDB documents
- File manager state in MongoDB

**Pros**: No file locking needed, inherently safe
**Cons**: Requires MongoDB always running, migration complexity

### B. File Locking Only (No Sessions)

Keep single history/state file, use fcntl locks everywhere.

**Pros**: Simpler code, no session management
**Cons**: Contention under heavy parallel load, blocking

### C. Hybrid (Recommended - This Plan)

Session isolation for per-instance state, file locking for shared resources (notes.md).

**Pros**: Best performance, minimal contention, crash-safe
**Cons**: More code paths to maintain

---

## Estimated Scope

- **New files**: 1 (`session.py`)
- **Modified files**: 6
- **Lines of code**: ~200-300 additions/modifications
- **Test files**: 2-3 new test modules

---

## Success Criteria

1. Can run 10 concurrent QQ instances without data corruption
2. Each instance has isolated history
3. Notes.md updates are serialized via locks
4. No race conditions in agent/default creation
5. Clean session resume functionality
6. All existing tests pass
7. New parallel execution tests pass
