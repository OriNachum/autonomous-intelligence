# Core Notes Reference

Protected, never-forgotten essential information stored in `memory/core.md`.

## Module

```python
from qq.memory.core_notes import CoreNotesManager
```

## Constructor

```python
mgr = CoreNotesManager(memory_dir="./memory")
# File: {memory_dir}/core.md
# Lock: {memory_dir}/core.lock
```

Default `memory_dir` from `MEMORY_DIR` env var or `./memory`.

## Protected Categories

| Category | Purpose | Examples |
|----------|---------|----------|
| `identity` | Name, location, role, preferences | "User's name is Alice" |
| `projects` | Active projects being worked on | "Working on QQ memory system" |
| `relationships` | Important people, collaborators | "John is the team lead" |
| `system` | Hardware, setup, configuration | "Running on Jetson Orin" |

## API

### Read Operations

```python
mgr.load_notes() -> str
```
Load or create `core.md`. Returns full content.

```python
mgr.get_notes() -> str
```
Get current content (loads if not already loaded).

```python
mgr.get_items_by_category(category: str) -> List[str]
```
Get all items in a category.

```python
mgr.get_all_items() -> Dict[str, List[str]]
```
All items grouped by category.

```python
mgr.is_protected(content: str) -> bool
```
Check if content exists in core notes.

### Write Operations

```python
mgr.add_core(content: str, category: str, source: str = "auto") -> bool
```
Add item to a protected category. Returns `True` if added (not duplicate).

```python
mgr.remove_core(pattern: str, category: str = None) -> bool
```
Remove items matching pattern. If `category` is None, searches all categories.

### Promotion

```python
CoreNotesManager.is_core_candidate(content: str) -> Tuple[bool, str]
```
Static method. Check if content should be promoted to core. Returns `(should_promote, suggested_category)`.

```python
mgr.suggest_promotion(content: str, importance: float) -> Optional[str]
```
Suggest promoting a note to core based on content patterns and importance score. Returns suggested category or None.

## Concurrency

- Uses `fcntl` file locking (shared reads, exclusive writes)
- Atomic writes via temp file + rename
- Safe for parallel QQ instances

## File Format

```markdown
# Core Memory
*Last updated: 2025-01-15T10:30:00*

## Identity
- User's name is Alice
- Prefers dark mode

## Projects
- Working on QQ memory system

## Relationships
- John is the team lead

## System
- Running on Jetson Orin with 64GB RAM
```
