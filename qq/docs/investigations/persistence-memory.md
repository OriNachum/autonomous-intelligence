# Memory Persistence Investigation

**Date:** 2026-02-04
**Scope:** All memory agents and persistence methods in QQ
**Status:** Complete

## Executive Summary

QQ implements a multi-layer memory persistence system using three storage backends:

1. **File-based Notes** (`notes.md`) - Markdown file with atomic writes and file locking
2. **MongoDB** - Document storage with vector embeddings for semantic search
3. **Neo4j** - Knowledge graph for entities and relationships

**Verdict:** All three systems correctly persist data between restarts. Docker volumes ensure database survival. File-based storage uses atomic writes. However, there are consistency gaps between the dual-write systems.

---

## 1. File-Based Notes Persistence

### Location
- **File:** `src/qq/memory/notes.py`
- **Storage:** `$MEMORY_DIR/notes.md` (default: `./memory/notes.md`)

### How It Works

```
NotesManager
├── notes.md (structured markdown with sections)
├── notes.lock (fcntl file lock)
└── atomic writes via temp file + os.replace()
```

### Persistence Mechanisms

| Mechanism | Implementation | Status |
|-----------|----------------|--------|
| Atomic writes | `tempfile.mkstemp()` + `os.replace()` | ✅ Working |
| File locking | `fcntl.flock()` exclusive/shared locks | ✅ Working |
| Auto-timestamp | `Last updated:` field on every save | ✅ Working |
| Session isolation | Lock prevents race conditions | ✅ Working |

### Code Analysis

**Atomic Write Pattern (notes.py:106-139):**
```python
def _save(self) -> None:
    with self._file_lock(exclusive=True):
        # Write to temp file first
        fd, tmp_path = tempfile.mkstemp(dir=self.memory_dir, suffix=".md.tmp")
        with os.fdopen(fd, 'w') as f:
            f.write(self._content)
        # Atomic rename (POSIX guarantee)
        os.replace(tmp_path, self.notes_file)
```

**File Locking (notes.py:43-62):**
```python
@contextmanager
def _file_lock(self, exclusive: bool = True):
    self.lock_file.touch(exist_ok=True)
    with open(self.lock_file, 'r') as f:
        fcntl.flock(f.fileno(), fcntl.LOCK_EX if exclusive else fcntl.LOCK_SH)
        yield
        fcntl.flock(f.fileno(), fcntl.LOCK_UN)
```

### Survival Across Restarts
- **YES** - File persists on disk
- Loads from disk on init via `load_notes()`
- In-memory cache (`_content`) is refreshed on each operation

### Potential Issues
1. Orphaned `.md.tmp` files if process crashes during write
2. Lock file (`notes.lock`) never cleaned up
3. No backup/versioning - deletions are permanent

---

## 2. MongoDB Notes Store

### Location
- **File:** `src/qq/memory/mongo_store.py`
- **Storage:** MongoDB database `qq_memory`, collection `notes`
- **Volume:** `./data/mongodb:/data/db` (docker-compose.yml:14)

### How It Works

```
MongoNotesStore
├── Database: qq_memory
├── Collection: notes
│   ├── note_id (unique index, SHA256 hash of content)
│   ├── content (note text)
│   ├── embedding (vector for similarity search)
│   ├── section (e.g., "Key Topics")
│   └── updated_at (datetime)
└── Indexes: note_id (unique), section, updated_at
```

### Persistence Mechanisms

| Mechanism | Implementation | Status |
|-----------|----------------|--------|
| Index creation | `_ensure_indexes()` on init | ✅ Working |
| Upsert pattern | `update_one(..., upsert=True)` | ✅ Working |
| Docker volume | `./data/mongodb:/data/db` | ✅ Working |
| Restart policy | `restart: unless-stopped` | ✅ Working |

### Code Analysis

**Upsert Pattern (mongo_store.py:50-81):**
```python
def upsert_note(self, note_id, content, embedding, section=None, metadata=None):
    doc = {
        "note_id": note_id,
        "content": content,
        "embedding": embedding,
        "updated_at": datetime.utcnow(),
    }
    self.collection.update_one(
        {"note_id": note_id},
        {"$set": doc},
        upsert=True,
    )
```

**Index Initialization (mongo_store.py:41-48):**
```python
def _ensure_indexes(self) -> None:
    self.collection.create_index("note_id", unique=True)
    self.collection.create_index("section")
    self.collection.create_index("updated_at")
```

### Survival Across Restarts
- **YES** - Data persists in Docker volume `./data/mongodb`
- MongoDB container has healthcheck and auto-restart
- Connection re-established on application restart

### Potential Issues
1. **Lazy initialization:** If MongoDB is unavailable at start, silently skipped for entire session
2. **No transactions:** Notes.md and MongoDB updates are independent operations
3. **Embedding regeneration:** If embedding model changes, stored embeddings become stale
4. **Unbounded growth:** No automatic cleanup of old notes

---

## 3. Neo4j Knowledge Graph

### Location
- **File:** `src/qq/knowledge/neo4j_client.py`
- **Storage:** Neo4j database
- **Volumes:** `./data/neo4j/data:/data`, `./data/neo4j/logs:/logs` (docker-compose.yml:31-32)

### How It Works

```
Neo4jClient
├── Entities (Nodes)
│   ├── Labels: Person, Concept, Topic, Location, Event
│   ├── Properties: name, description, embedding
│   └── Pattern: MERGE by name (upsert)
├── Relationships
│   ├── Types: RELATES_TO, KNOWS, etc.
│   └── Pattern: MERGE (source)-[r:TYPE]->(target)
└── Connection: bolt://localhost:7687
```

### Persistence Mechanisms

| Mechanism | Implementation | Status |
|-----------|----------------|--------|
| Entity upsert | Cypher `MERGE (n:Type {name: $name})` | ✅ Working |
| Relationship upsert | Cypher `MERGE (a)-[r:TYPE]->(b)` | ✅ Working |
| Docker volume | `./data/neo4j/data:/data` | ✅ Working |
| Restart policy | Default (always restart) | ✅ Working |

### Code Analysis

**Entity Creation (neo4j_client.py:62-97):**
```python
def create_entity(self, entity_type, name, properties=None, embedding=None):
    query = f"""
        MERGE (n:{entity_type} {{name: $name}})
        SET {prop_items}
        RETURN n.name as id
    """
    result = self.execute(query, props)
    return result[0]["id"] if result else name
```

**Relationship Creation (neo4j_client.py:99-137):**
```python
def create_relationship(self, source_name, target_name, relationship_type, properties=None):
    query = f"""
        MERGE (a {{name: $source}})
        MERGE (b {{name: $target}})
        MERGE (a)-[r:{relationship_type}]->(b)
        {set_clause}
        RETURN type(r) as rel_type
    """
```

### Survival Across Restarts
- **YES** - Data persists in Docker volume `./data/neo4j/data`
- Neo4j container has healthcheck
- Connection re-established on application restart via lazy initialization

### Potential Issues
1. **Duplicate entities:** Extraction quality depends on LLM; "John" and "John Smith" stored separately
2. **No label on relationship MERGE:** Creates label-less nodes if entities don't exist yet
3. **Silent failures:** Errors logged but not propagated
4. **Connection not closed:** `close()` method exists but rarely called

---

## 4. Conversation History

### Location
- **File:** `src/qq/history.py`
- **Storage:** `~/.qq/<agent>/sessions/<session_id>/history.json`

### Persistence Mechanisms

| Mechanism | Implementation | Status |
|-----------|----------------|--------|
| Per-session isolation | Unique session directory | ✅ Working |
| Atomic writes | `tempfile.mkstemp()` + `os.replace()` | ✅ Working |
| Auto-save | Save after every `add()` call | ✅ Working |
| Session resume | `QQ_SESSION_ID` env var | ✅ Working |

### Code Analysis

**Atomic Save (history.py:65-87):**
```python
def _save(self) -> None:
    fd, tmp_path = tempfile.mkstemp(dir=self.session_dir, suffix=".json.tmp")
    with os.fdopen(fd, 'w') as f:
        json.dump({"messages": self._messages}, f, indent=2)
    os.replace(tmp_path, self.history_file)
```

### Survival Across Restarts
- **YES** - JSON files persist in `~/.qq/` directory
- Each session has isolated history
- Can resume with `QQ_SESSION_ID=<id> ./qq`

### Potential Issues
1. **Session accumulation:** Old sessions never cleaned up
2. **Unbounded file size:** Full history kept, only windowed for API calls
3. **No backup:** Single file, no redundancy

---

## 5. Data Flow and Integration

### Write Path

```
User Message
    ↓
┌─────────────────────────────────────────────────┐
│ app.py - Main conversation loop                 │
├─────────────────────────────────────────────────┤
│ 1. history.add(user_message)  → ~/.qq/.../history.json
│ 2. agent(message)             → LLM inference
│ 3. history.add(response)      → ~/.qq/.../history.json
│ 4. notes_agent.process()      → notes.md + MongoDB
│ 5. knowledge_agent.process()  → Neo4j
└─────────────────────────────────────────────────┘
```

### Notes Agent Dual-Write (notes/notes.py:224-266)

```python
def _apply_updates(self, updates):
    # Update 1: Markdown file
    self.notes_manager.apply_diff(additions, removals)

    # Update 2: MongoDB with embeddings
    if self.mongo_store and self.embeddings:
        for addition in additions:
            embedding = self.embeddings.get_embedding(item)
            self.mongo_store.upsert_note(note_id, content, embedding)
```

### Knowledge Graph Agent (services/graph.py:82-117)

```python
def process_messages(self, messages):
    # Step 1: Extract entities via LLM
    entities_list = self.entity_agent.extract(messages)

    # Step 2: Extract relationships via LLM
    relationships = self.relationship_agent.extract(messages, entities_list)

    # Step 3: Store in Neo4j
    self._store_extraction({"entities": entities_list, "relationships": relationships})
```

---

## 6. Docker Volume Configuration

From `docker-compose.yml`:

| Service | Volume Mount | Purpose |
|---------|--------------|---------|
| MongoDB | `./data/mongodb:/data/db` | Database files |
| Neo4j | `./data/neo4j/data:/data` | Graph database |
| Neo4j | `./data/neo4j/logs:/logs` | Transaction logs |
| TEI | `./data/tei:/root/.cache/huggingface` | Model cache |

All volumes are bind mounts to `./data/` directory, ensuring data survives container restarts.

---

## 7. Validation Summary

### What Persists Between Restarts

| Component | Storage | Persists | Verified |
|-----------|---------|----------|----------|
| Notes (markdown) | `./memory/notes.md` | ✅ Yes | Atomic writes |
| Notes (MongoDB) | `./data/mongodb/` | ✅ Yes | Docker volume |
| Knowledge graph | `./data/neo4j/data/` | ✅ Yes | Docker volume |
| Conversation history | `~/.qq/` | ✅ Yes | JSON files |
| Embeddings model | `./data/tei/` | ✅ Yes | Docker volume |

### What Does NOT Persist

| Component | Reason |
|-----------|--------|
| In-memory caches | Python process restart clears memory |
| Lock file state | Lock released on process exit |
| Active connections | Re-established on startup |

---

## 8. Critical Issues Found

### High Severity

1. **Dual-Write Consistency Gap**
   - Notes.md and MongoDB are updated independently
   - If one fails, data becomes inconsistent
   - No transaction coordination between file and database

2. **Silent Database Failures**
   - Lazy initialization fails silently (logged, not raised)
   - Application continues without persistence to MongoDB/Neo4j
   - User unaware data not being saved

3. **Entity Duplication in Neo4j**
   - MERGE by name only; "John" vs "John Smith" creates duplicates
   - No entity resolution or deduplication

### Medium Severity

4. **No Data Cleanup**
   - Session directories accumulate in `~/.qq/`
   - MongoDB notes never expire
   - Neo4j entities never pruned

5. **Embedding Staleness**
   - Embeddings generated once, never updated
   - If embedding model changes, vectors incompatible

6. **Connection Lifecycle**
   - Neo4j driver never explicitly closed
   - MongoDB client kept open for app lifetime

### Low Severity

7. **Orphaned Temp Files**
   - `.md.tmp` and `.json.tmp` files if crash during write
   - Lock files accumulate

---

## 9. Recommendations

1. **Add consistency checks** on startup comparing notes.md with MongoDB
2. **Implement health monitoring** for database connections
3. **Add session cleanup** (delete sessions older than N days)
4. **Propagate errors** instead of silent logging
5. **Add data export/backup** functionality
6. **Implement entity resolution** for knowledge graph

---

## 10. Conclusion

The QQ memory system **correctly persists data between restarts** through:
- Atomic file writes with locking for notes.md
- Docker volumes for MongoDB and Neo4j databases
- Session-isolated JSON files for conversation history

The main gap is **consistency between the dual-write systems** (notes.md + MongoDB) which can diverge on partial failures. For production use, transaction coordination or eventual consistency reconciliation should be implemented.
