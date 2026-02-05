# Flat Notes Storage (MongoDB RAG)

The flat notes storage provides vector-searchable notes using MongoDB with embeddings for Retrieval Augmented Generation (RAG).

## Overview

| Property | Value |
|----------|-------|
| **Agent** | `NotesAgent` |
| **Source** | `src/qq/memory/notes_agent.py` |
| **Storage** | MongoDB |
| **Store** | `MongoNotesStore` (`src/qq/memory/mongo_store.py`) |
| **Port** | 27017 |

## Architecture

```
Conversation Messages
        │
        ▼
┌───────────────────┐
│    NotesAgent     │  Analyzes last 20 messages
└─────────┬─────────┘
          │
          ▼
┌───────────────────┐
│  Extract Changes  │  Identifies additions and removals
└─────────┬─────────┘
          │
          ├──────────────────────┐
          ▼                      ▼
┌───────────────────┐  ┌───────────────────┐
│   notes.md File   │  │ MongoDB + Vectors │
│   (Human-readable)│  │   (RAG Search)    │
└───────────────────┘  └───────────────────┘
```

## MongoDB Schema

| Field | Type | Description |
|-------|------|-------------|
| `note_id` | string | SHA-256 hash of content (unique identifier) |
| `content` | string | The text content of the note |
| `section` | string | Logical section (Key Topics, Important Facts, etc.) |
| `embedding` | list[float] | Vector embedding for similarity search |
| `importance` | float | Importance score (0.0-1.0, default: 0.5) |
| `decay_rate` | float | How fast importance decays (default: 0.01) |
| `access_count` | int | Number of times note was accessed |
| `created_at` | datetime | When note was created |
| `updated_at` | datetime | When note was last modified |
| `last_accessed` | datetime | When note was last retrieved |
| `metadata` | object | Additional metadata |

### Indexes

```javascript
db.notes.createIndex({ "note_id": 1 }, { unique: true })
db.notes.createIndex({ "section": 1 })
db.notes.createIndex({ "updated_at": -1 })
db.notes.createIndex({ "importance": -1 })
db.notes.createIndex({ "last_accessed": 1 })
```

## Sections

Notes are organized into logical sections:

| Section | Purpose |
|---------|---------|
| `Key Topics` | Main topics discussed |
| `Important Facts` | Factual information |
| `People & Entities` | People, organizations mentioned |
| `Ongoing Threads` | Active discussions, tasks |
| `File Knowledge` | Information about files |

## Importance Scoring

Notes have dynamic importance scores that affect retrieval:

- **Initial Score**: New notes start at 0.5 importance
- **Access Boost**: Accessing a note increases importance
- **Time Decay**: Unused notes decay over time
- **Promotion**: High-importance notes (>0.8) may be promoted to [Core Notes](./memory-notes-core.md)

### Importance-Based Operations

```python
# Get notes by importance range
store.get_by_importance_range(min_importance=0.7, max_importance=1.0)

# Get stale notes (not accessed in 30 days)
store.get_stale_notes(days_threshold=30)

# Bulk update importance scores
store.bulk_update_importance([
    {"note_id": "abc123", "importance": 0.8},
    {"note_id": "def456", "importance": 0.3},
])
```

## Vector Search

The system uses cosine similarity for note retrieval:

```python
# Search for similar notes
results = store.search_similar(
    query_embedding=embedding_client.get_embedding("Python programming"),
    limit=5,
    section="Key Topics"  # Optional filter
)
```

Returns:
```python
[
    {
        "note_id": "abc123",
        "content": "Python is a programming language...",
        "section": "Key Topics",
        "score": 0.89,
        "metadata": {}
    },
    ...
]
```

### Implementation Note

Currently uses manual cosine similarity calculation for portability:
```python
def cosine_similarity(v1, v2):
    dot_product = sum(a * b for a, b in zip(v1, v2))
    norm1 = sqrt(sum(a * a for a in v1))
    norm2 = sqrt(sum(b * b for b in v2))
    return dot_product / (norm1 * norm2)
```

For production scale, consider MongoDB Atlas Vector Search.

## NotesAgent

Source: `src/qq/memory/notes_agent.py`

The NotesAgent analyzes conversations and extracts note changes:

1. Takes the last 20 messages from conversation
2. Uses LLM to identify:
   - New information to add
   - Outdated information to remove
3. Applies changes to both:
   - `notes.md` file (human-readable)
   - MongoDB store (vector-searchable)

### Prompt Template

The agent uses `notes.user.md` prompt to extract structured changes:
```json
{
  "additions": [
    {"section": "Key Topics", "item": "New topic discussed"}
  ],
  "removals": ["Outdated information pattern"]
}
```

## Deduplication

Source: `src/qq/memory/deduplication.py`

Prevents duplicate notes using:
- Content hashing (SHA-256)
- Semantic similarity checking
- Fuzzy matching for near-duplicates

## Archive System

Source: `src/qq/memory/archive.py`

Low-importance notes can be archived:
- Moves notes below importance threshold
- Preserves for potential future retrieval
- Reduces active note count

## API Reference

### MongoNotesStore Methods

| Method | Description |
|--------|-------------|
| `upsert_note()` | Insert or update a note |
| `get_note()` | Get note by ID |
| `delete_note()` | Delete note by ID |
| `search_similar()` | Vector similarity search |
| `get_recent_notes()` | Get recently updated notes |
| `increment_access()` | Track note access |
| `update_importance()` | Update importance score |
| `get_by_importance_range()` | Filter by importance |
| `get_stale_notes()` | Get unused notes |
| `bulk_update_importance()` | Batch importance updates |
| `clear_all()` | Clear all notes |

## Related Documentation

- [Memory Overview](./memory.md)
- [Core Notes](./memory-notes-core.md)
- [Ephemeral Notes](./memory-notes-ephemeral.md)
