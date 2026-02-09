# Working Notes Reference

Per-agent working memory with file-based persistence. Main agent uses `notes.md`, child agents use `notes.{id}.md` for isolation.

## Module

```python
from qq.memory.notes import NotesManager, get_notes_manager
```

## Constructor

```python
# Main agent notes
mgr = get_notes_manager("./memory")

# Ephemeral (per-agent) notes
mgr = NotesManager(memory_dir="./memory", notes_id="child_abc")
# File: memory/notes.child_abc.md

# Create ephemeral with initial context
mgr = NotesManager.create_ephemeral("child_abc", "Initial context here", "./memory")
```

`get_notes_manager()` reads `QQ_NOTES_ID` env var to determine if ephemeral.

## Sections

| Section | Purpose |
|---------|---------|
| `Key Topics` | Main themes of conversation |
| `Important Facts` | Specific facts, decisions, data points |
| `People & Entities` | People, organizations, projects mentioned |
| `Ongoing Threads` | Open questions, unresolved topics |
| `File Knowledge` | Files analyzed or referenced |

## API

### Read Operations

```python
mgr.load_notes() -> str
```
Load from disk.

```python
mgr.get_notes() -> str
```
Get current content (loads if needed).

```python
mgr.get_all_items() -> List[dict]
```
All items across sections. Each dict: `{"section": str, "item": str}`.

```python
mgr.get_section_items(section: str) -> List[str]
```
Items from one section.

```python
mgr.count_items() -> int
```
Total item count across all sections.

### Write Operations

```python
mgr.add_item(section: str, item: str) -> bool
```
Add item to section. Returns `False` if duplicate detected.

```python
mgr.remove_item(section: str, item_pattern: str) -> bool
```
Remove first item matching pattern (substring match).

```python
mgr.remove_exact_item(item: str) -> bool
```
Remove exact match across all sections.

```python
mgr.update_section(section: str, items: List[str]) -> None
```
Replace entire section contents.

```python
mgr.apply_diff(
    additions: List[dict],  # [{"section": str, "item": str}, ...]
    removals: List[str]      # items to remove (exact match)
) -> None
```
Batch add/remove in one atomic operation.

```python
mgr.rebuild_with_items(items: List[dict]) -> None
```
Rebuild entire notes from scratch. Each dict: `{"section": str, "item": str}`.

### Ephemeral Lifecycle

```python
mgr.is_ephemeral  # True if notes_id is set
mgr.cleanup() -> bool  # Remove ephemeral file (only if is_ephemeral)
```

## Concurrency

- `fcntl` locking (shared reads, exclusive writes)
- Atomic writes via temp file + rename
- Per-agent file isolation prevents cross-contamination

## File Format

```markdown
# Working Memory
*Updated: 2025-01-15T10:30:00*

## Key Topics
- QQ memory architecture
- Multi-layer notes system

## Important Facts
- MongoDB stores notes with vector embeddings
- Neo4j stores entity relationships

## People & Entities
- Alice (user)
- John (team lead)

## Ongoing Threads
- How to implement entity merging?

## File Knowledge
- src/qq/memory/mongo_store.py: MongoDB notes store implementation
```
