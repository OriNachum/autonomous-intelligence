# Memory Indexing (MongoDB)

Notes are the primary knowledge unit in QQ. They are stored in MongoDB with vector embeddings, importance scores, access tracking, and source provenance.

## MongoDB Document Schema

Collection: `notes` (in `mongo_store.py:12-131`)

```json
{
  "note_id": "string (unique, SHA256(content)[:16])",
  "content": "string",
  "embedding": [float, ...],
  "section": "Key Topics | Important Facts | People & Entities | Ongoing Threads | File Knowledge",
  "metadata": {},
  "updated_at": "datetime",
  "created_at": "datetime",
  "access_count": 0,
  "last_accessed": "datetime",
  "importance": 0.4,
  "decay_rate": 0.01,
  "source": { "SourceRecord fields" },
  "source_history": [ { "SourceRecord fields" }, ... ]
}
```

## Indexes

Created in `mongo_store.py:45-60`:

| Index | Purpose |
|-------|---------|
| `note_id` (unique) | Fast lookups |
| `section` | Filter by section |
| `updated_at` | Recency queries |
| `importance` | Importance-based filtering |
| `last_accessed` | Staleness detection |
| `source.file_path` | Provenance queries |
| `source.source_type` | Source type filtering |
| `source.source_id` | Source identity lookups |

## Vector Search

`search_similar()` (`mongo_store.py:147-202`):

1. Compute embedding for the query text
2. Cosine similarity: `dot_product / (norm1 * norm2)` against all stored embeddings
3. Optional section filtering
4. Return top-k results sorted by similarity score

Note: This is an in-process Python implementation. For production scale, MongoDB Atlas Vector Search can be used.

## Access Tracking

`increment_access()` (`mongo_store.py:250-267`):
- Incremented each time a note is retrieved for context
- Updates `access_count` and `last_accessed` timestamp
- Feeds into the importance decay formula (more accesses = slower decay)

## Importance Management

- `update_importance()` -- clamp value to `[0.0, 1.0]`
- `get_by_importance_range()` -- fetch notes within an importance band
- `get_stale_notes()` -- find notes not accessed in N days
- `bulk_update_importance()` -- batch update for decay runs

## Notes File Persistence (`notes.md`)

Defined in `src/qq/memory/notes.py:42-539`.

Notes are also persisted to a markdown file with section headers:

```markdown
## Key Topics
## Important Facts
## People & Entities
## Ongoing Threads
## File Knowledge
```

### File Locking

`_file_lock()` (`notes.py:154-173`) uses `fcntl` exclusive/shared locks for concurrent access across multiple QQ instances.

### Operations

- `add_item()` -- add to section if not already present
- `remove_item()` -- remove items matching regex
- `update_section()` -- replace all items in a section
- `apply_diff()` -- process additions and removals atomically
- Atomic saves: write to temp file + rename to prevent corruption

### Per-Agent Ephemeral Notes

`get_notes_manager()` (`notes.py:25-39`) returns a manager for either:
- `notes.md` (root agent)
- `notes.{notes_id}.md` (sub-agent ephemeral working memory)

The `QQ_NOTES_ID` env var auto-selects the right file. Ephemeral files are cleaned up after task completion.

## Core Notes (`core.md`)

Defined in `src/qq/memory/core_notes.py:61-386`.

Protected categories that are **never automatically forgotten**:

| Category | Examples |
|----------|----------|
| Identity | User's name, role, location, contact |
| Projects | Active projects, systems being built |
| Relationships | Known people, teams, organizations |
| System | Technical setup, preferences |

### Auto-Detection & Promotion

`is_core_candidate()` (`core_notes.py:334-364`) uses pattern matching:
- **Identity patterns**: "my name", "i am", "i live", "my email"
- **Project patterns**: "my project", "i'm building", "our system"

Notes with importance > 0.8 are candidates for promotion to core via `suggest_promotion()`.
