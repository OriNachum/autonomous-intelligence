---
name: mongodb-query
description: Query MongoDB notes store for memory analysis and statistics.
triggers:
  - mongodb
  - mongo
  - notes store
  - memory storage
  - notes query
---

# MongoDB Query Skill

Query the MongoDB notes store to investigate memory contents, embeddings, and note statistics.

## Connection Details

- **URI**: `mongodb://localhost:27017` (or `MONGODB_URI` env var)
- **Database**: `qq_memory`
- **Collection**: `notes`

## Python Usage

```python
from qq.memory.mongo_store import MongoNotesStore

# Initialize store
store = MongoNotesStore()

# Get a specific note
note = store.get_note("note_id_here")

# Get recent notes
recent = store.get_recent_notes(limit=10)

# Get notes by importance range
important = store.get_by_importance_range(min_importance=0.7, max_importance=1.0)

# Get stale notes (not accessed recently)
stale = store.get_stale_notes(days_threshold=30)
```

## Direct PyMongo Usage

```python
from pymongo import MongoClient

client = MongoClient("mongodb://localhost:27017")
db = client["qq_memory"]
notes = db["notes"]

# Count all notes
total = notes.count_documents({})

# Find all notes
all_notes = list(notes.find({}, {"content": 1, "section": 1, "importance": 1}))

# Count by section
pipeline = [
    {"$group": {"_id": "$section", "count": {"$sum": 1}}},
    {"$sort": {"count": -1}}
]
by_section = list(notes.aggregate(pipeline))

# Find notes without embeddings
no_embedding = notes.count_documents({"embedding": None})

# Sample notes
sample = list(notes.find().limit(10))
```

## CLI Usage

```bash
# Use mongosh directly
docker exec -it qq-mongodb-1 mongosh qq_memory --eval "db.notes.countDocuments({})"

# Get collection stats
docker exec -it qq-mongodb-1 mongosh qq_memory --eval "db.notes.stats()"
```

## Notes Schema

Each note document contains:
- `note_id`: Unique identifier
- `content`: Note text
- `embedding`: Vector embedding (list of floats)
- `section`: Category (e.g., "Key Topics", "Preferences")
- `metadata`: Additional key-value pairs
- `importance`: Score 0.0-1.0 (default 0.5)
- `decay_rate`: How fast importance decays (default 0.01)
- `access_count`: Number of times accessed
- `last_accessed`: Timestamp of last access
- `created_at`: Creation timestamp
- `updated_at`: Last update timestamp
