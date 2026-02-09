# MongoDB RAG Reference

Vector-search-enabled notes store with importance scoring, time decay, deduplication, archival, and source provenance.

## Table of Contents

- [MongoNotesStore](#mongonotesstore)
- [ImportanceScorer](#importancescorer)
- [NoteDeduplicator](#notededuplicator)
- [ArchiveManager](#archivemanager)
- [Document Schema](#document-schema)

## MongoNotesStore

```python
from qq.memory.mongo_store import MongoNotesStore

store = MongoNotesStore(
    uri="mongodb://localhost:27017",  # or MONGODB_URI env var
    database="qq_memory",
    collection="notes"
)
```

### CRUD

```python
store.upsert_note(
    note_id: str,
    content: str,
    embedding: List[float],
    section: str,
    metadata: dict = None,
    importance: float = 0.5,
    decay_rate: float = 0.01,
    source: dict = None
) -> None
```

```python
store.get_note(note_id: str) -> Optional[Dict]
# Returns: {note_id, content, section, importance, access_count}
```

```python
store.get_full_note(note_id: str) -> Optional[Dict]
# Returns all fields including embedding, metadata, source, source_history
```

```python
store.delete_note(note_id: str) -> bool
```

```python
store.clear_all() -> int
# Returns count of deleted documents
```

### Search

```python
store.search_similar(
    query_embedding: List[float],
    limit: int = 5,
    section: str = None
) -> List[Dict]
# Returns: [{note_id, content, section, importance, score}, ...]
# score = cosine similarity (0-1)
```

```python
store.get_recent_notes(limit: int = 10, section: str = None) -> List[Dict]
# Sorted by updated_at descending
```

```python
store.get_by_importance_range(
    min_importance: float = 0.0,
    max_importance: float = 1.0,
    limit: int = 20
) -> List[Dict]
```

```python
store.get_stale_notes(days_threshold: int = 30, limit: int = 20) -> List[Dict]
# Notes not accessed within days_threshold
```

### Access & Importance

```python
store.increment_access(note_id: str) -> bool
# Bumps access_count by 1, updates last_accessed to now
```

```python
store.update_importance(note_id: str, importance: float) -> bool
```

```python
store.bulk_update_importance(updates: List[Dict]) -> int
# Each dict: {"note_id": str, "importance": float}
# Returns count of updated documents
```

### Source Provenance

```python
store.append_source_history(
    note_id: str,
    source: dict,
    boost_importance: float = 0.0
) -> bool
# Appends to source_history array, optionally boosts importance
```

```python
store.find_by_source_file(file_path: str, limit: int = 20) -> List[Dict]
# Find notes extracted from a specific file
```

## ImportanceScorer

```python
from qq.memory.importance import ImportanceScorer, ScoredNote

scorer = ImportanceScorer()
```

### Scoring

```python
scorer.score_note(content: str, section: str, importance_hint: float = None) -> float
# Returns 0.0-1.0
```

Importance levels:
- **1.0** (Core): identity, preferences, projects
- **0.7** (High): specific decisions, important facts
- **0.4** (Medium): research topics, ongoing investigations
- **0.2** (Low): temporary observations, single-mention facts

Scoring factors: identity patterns (+0.3-0.5), project patterns (+0.3), specificity (dates/URLs/versions +0.05-0.1), section weights, length penalties.

```python
scorer.classify_importance(content: str, section: str) -> str
# Returns: "core", "high", "medium", or "low"
```

### Decay

```python
scorer.decay_importance(note: ScoredNote, current_time: datetime = None) -> float
# Returns decayed importance value
```

Decay formula:
```
access_bonus = min(0.5, access_count * 0.05)
age_factor = 1.0 / (1 + days_since_creation * 0.01)
staleness = days_since_access * decay_rate
decayed = (importance - staleness + access_bonus) * age_factor
```

```python
scorer.decay_notes(notes: List[ScoredNote], current_time=None) -> List[Tuple[ScoredNote, float]]
# Returns [(note, new_importance), ...]
```

### Candidates

```python
scorer.get_archival_candidates(notes, threshold=0.05, current_time=None) -> List[ScoredNote]
# Notes whose decayed importance falls below threshold
```

```python
scorer.get_promotion_candidates(notes, threshold=0.8) -> List[ScoredNote]
# Notes with importance above threshold (candidates for core notes)
```

```python
scorer.should_retrieve(note, threshold=0.2, current_time=None) -> bool
# Whether a note's decayed importance is above retrieval threshold
```

### Configuration

| Env Var | Default | Description |
|---------|---------|-------------|
| `QQ_CORE_THRESHOLD` | 0.8 | Promote to core above this |
| `QQ_ARCHIVE_THRESHOLD` | 0.05 | Archive below this |
| `QQ_MIN_RETRIEVAL_IMPORTANCE` | 0.2 | Skip in RAG below this |
| `QQ_BASE_DECAY_RATE` | 0.01 | Default decay rate |

## NoteDeduplicator

```python
from qq.memory.deduplication import NoteDeduplicator

dedup = NoteDeduplicator(mongo_store, embedding_client)
```

### Find Duplicates

```python
dedup.find_similar(threshold: float = 0.85, section: str = None) -> List[DuplicatePair]
# DuplicatePair: {note_a, note_b, similarity}
```

```python
dedup.find_exact_duplicates(notes_content: List[str]) -> List[Tuple[str, str]]
# Exact text matches
```

### Consolidate

```python
dedup.consolidate(note_a, note_b, use_llm: bool = False, model=None) -> ScoredNote
# Simple: keep primary, combine metadata
# LLM: intelligently merge content
```

```python
dedup.run_consolidation_pass(
    archive_manager: ArchiveManager,
    use_llm: bool = False,
    model = None
) -> ConsolidationReport
# Full pass: find duplicates, consolidate, archive secondary
# ConsolidationReport: {pairs_found, consolidated, errors}
```

```python
dedup.should_consolidate() -> bool
# True if note count > QQ_MAX_WORKING_NOTES (default: 100)
```

### Configuration

| Env Var | Default | Description |
|---------|---------|-------------|
| `QQ_DEDUP_THRESHOLD` | 0.85 | Cosine similarity threshold |
| `QQ_MAX_WORKING_NOTES` | 100 | Trigger consolidation above this |

## ArchiveManager

```python
from qq.memory.archive import ArchiveManager

archive = ArchiveManager(memory_dir="./memory")
# File: {memory_dir}/archive.jsonl
```

### Archive

```python
archive.archive_note(note_id: str, reason: str, remove_from_mongo: bool = True) -> bool
# Moves note to archive.jsonl, optionally removes from MongoDB
```

```python
archive.archive_low_importance(threshold: float = 0.05) -> int
# Bulk archive notes below threshold. Returns count.
```

### Restore

```python
archive.restore_note(note_id: str, boost_importance: float = 0.1) -> bool
# Restore from archive back to MongoDB with importance boost
```

### Search & Stats

```python
archive.search_archive(query: str, limit: int = 10, include_restored: bool = False) -> List[ArchivedNote]
```

```python
archive.get_archive_stats() -> Dict[str, Any]
# {total, by_reason, oldest, newest}
```

```python
archive.purge_old_archives(days: int = 90) -> int
# Delete archives older than N days. Returns count.
```

### Configuration

| Env Var | Default | Description |
|---------|---------|-------------|
| `QQ_ARCHIVE_RETENTION_DAYS` | 90 | Purge after this many days |
| `ARCHIVE_THRESHOLD` | 0.05 | Low importance threshold |

## Document Schema

```json
{
  "note_id": "note_abc123",
  "content": "QQ uses MongoDB for notes storage",
  "embedding": [0.1, 0.2, ...],
  "section": "Key Topics",
  "metadata": {},
  "importance": 0.7,
  "decay_rate": 0.01,
  "access_count": 5,
  "last_accessed": "2025-01-15T10:30:00Z",
  "created_at": "2025-01-10T08:00:00Z",
  "updated_at": "2025-01-15T10:30:00Z",
  "source": {
    "source_type": "file",
    "file_path": "/path/to/file.py",
    "checksum": "abc123",
    "git_metadata": {"branch": "main", "commit": "..."},
    "analyzed_at": "2025-01-10T08:00:00Z"
  },
  "source_history": [
    {"source_type": "conversation", "session_id": "...", "agent_id": "..."}
  ]
}
```

### Indexes

- `note_id` (unique)
- `section`
- `updated_at`
- `importance`
- `last_accessed`
- `source.file_path` (sparse)
- `source.source_type` (sparse)
- `source.source_id` (sparse)
