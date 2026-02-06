# Source Metadata & Provenance Tracking

Every piece of knowledge stored in QQ's memory systems (MongoDB notes, Neo4j entities and relationships) is linked back to its origin. This allows the system to cite sources when answering, verify content integrity via checksums, and assess source quality through git authorship.

## Overview

| Property | Value |
|----------|-------|
| **Module** | `src/qq/memory/source.py` |
| **Stores** | MongoDB (subdocument), Neo4j (Source node) |
| **Collected at** | File read time and conversation extraction time |

## How It Works

```
File Read (FileManager)              Conversation
       │                                  │
       ▼                                  ▼
 compute checksum               collect session/agent ID
 collect git metadata
       │                                  │
       ▼                                  ▼
   SourceRecord ◄─────────────────── SourceRecord
       │
       ├──► MongoDB: stored as `source` subdocument on each note
       │
       └──► Neo4j:   stored as a :Source node, linked via EXTRACTED_FROM
```

When a file is read through `FileManager.read_file()`, the system automatically computes a SHA-256 checksum of the file and collects git metadata (repo, branch, commit, author). This information travels through the extraction pipeline and gets attached to every note, entity, and relationship derived from that file.

## SourceRecord

The `SourceRecord` dataclass (`src/qq/memory/source.py`) carries all provenance fields:

| Field | Type | Description |
|-------|------|-------------|
| `source_type` | string | `"file"`, `"conversation"`, `"user_input"`, or `"derived"` |
| `file_path` | string | Absolute path at time of read |
| `file_name` | string | Basename for display |
| `line_start` | int | Start line extracted from |
| `line_end` | int | End line extracted from |
| `checksum` | string | `sha256:<hex>` of file content at read time |
| `git_repo` | string | Repository remote URL or root path |
| `git_branch` | string | Branch name at read time |
| `git_commit` | string | Last commit hash touching this file |
| `git_author` | string | Author of that commit |
| `session_id` | string | QQ session ID |
| `agent_id` | string | Agent that performed extraction |
| `timestamp` | string | ISO timestamp of extraction |
| `confidence` | float | LLM extraction confidence |
| `source_id` | string | Unique ID (checksum for files, `session:<id>` for conversations) |

## MongoDB Storage

Notes store source as a subdocument:

```
{
  "note_id": "abc123",
  "content": "Project uses React 19",
  "source": {
    "source_type": "file",
    "file_path": "/home/user/project/package.json",
    "file_name": "package.json",
    "checksum": "sha256:e84319a...",
    "git_repo": "https://github.com/org/repo",
    "git_commit": "a1b2c3d",
    "git_author": "alice",
    "source_id": "sha256:e84319a..."
  },
  "source_history": [ ... ]
}
```

When a note is updated from a different source, the new source replaces `source` and the previous one is appended to `source_history`. This creates an audit trail showing every source that confirmed or updated a fact.

**Indexes**: `source.file_path`, `source.source_type`, `source.source_id` (all sparse).

## Neo4j Storage

Sources are modeled as first-class **Source nodes** rather than flat properties on entities. This enables graph traversal from any entity back to its origin.

### Source Node Schema

```cypher
(:Source {
  source_id: "sha256:e84319a...",
  source_type: "file",
  file_path: "/home/user/project/package.json",
  file_name: "package.json",
  checksum: "sha256:e84319a...",
  git_repo: "https://github.com/org/repo",
  git_branch: "main",
  git_commit: "a1b2c3d",
  git_author: "alice",
  session_id: "sess_123",
  mongo_note_ids: ["abc123", "def456"],
  created_at: datetime(),
  last_verified: datetime(),
  verified: true
})
```

### Relationships

```
(entity:Person)-[:EXTRACTED_FROM]->(source:Source)
(source:Source)-[:EVIDENCES {rel_source, rel_type}]->(target_entity)
```

- **EXTRACTED_FROM**: Every extracted entity links to its Source node
- **EVIDENCES**: Links a Source to the target entity of a relationship it evidences (since Neo4j edges can't point to other edges)

Entities also carry `source_first_id` (set on creation) and `source_latest_id` (updated on each mention) as flat properties for quick lookups without traversal.

### Querying Sources

Find all sources for an entity:
```cypher
MATCH (e {name: "Alice"})-[:EXTRACTED_FROM]->(s:Source)
RETURN s.file_name, s.git_author, s.verified
```

Find all knowledge from a specific file:
```cypher
MATCH (s:Source {file_path: "/path/to/file.md"})<-[:EXTRACTED_FROM]-(e)
RETURN e.name, labels(e)[0] as type
```

Cross-reference with MongoDB:
```cypher
MATCH (s:Source {source_id: "sha256:e84319a..."})
RETURN s.mongo_note_ids
```

## MongoDB-Neo4j Link

Both stores share the same `source_id` (derived from checksum for files, session ID for conversations):

- **MongoDB note** `source.source_id` -> query Neo4j for the `:Source` node and all linked entities
- **Neo4j entity** -> traverse `EXTRACTED_FROM` -> `:Source` node -> read `mongo_note_ids` -> fetch full note content from MongoDB

## Checksum Validation

The `validate_checksum()` function re-reads a file and compares its current SHA-256 against the stored checksum:

```python
from qq.memory.source import SourceRecord, validate_checksum

source = SourceRecord.from_dict(note["source"])
result = validate_checksum(source)
# True  = file unchanged (content verified)
# False = file modified since extraction (stale)
# None  = not a file source, or file missing
```

## Preserved Through Lifecycle

Source metadata is preserved across all memory operations:

| Operation | Behavior |
|-----------|----------|
| **Note creation** | Source attached as subdocument + Source node created in Neo4j |
| **Note update** | New source replaces current, old pushed to `source_history` |
| **Deduplication** | Secondary note's source merged into primary's `source_history` |
| **Archival** | `source` and `source_history` preserved in archive JSONL |
| **Restore** | Source metadata restored along with note content |

## Pipeline Integration

The source metadata flows through the extraction pipeline via `file_sources`, `session_id`, and `agent_id` parameters:

```
FileManager.read_file()
    ├── computes checksum + git metadata
    └── attaches to pending_file_reads
            │
            ▼
app.py (session-level file_sources registry)
            │
    ┌───────┴───────┐
    ▼               ▼
NotesAgent      KnowledgeGraphAgent
    │               │
    ▼               ├── create_source() -> Source node
MongoDB             ├── create_entity() + link_entity_to_source()
(source subdoc)     └── create_relationship() + link_relationship_to_source()
```

## Neo4jClient Methods

| Method | Description |
|--------|-------------|
| `create_source(source_record)` | MERGE a Source node (idempotent by source_id) |
| `link_entity_to_source(entity_name, source_id)` | Create EXTRACTED_FROM edge |
| `link_relationship_to_source(source, target, rel_type, source_id)` | Create EVIDENCES edge |
| `update_source_verification(source_id, verified)` | Update checksum validity |
| `get_sources_for_entity(entity_name)` | Get all Source nodes for an entity |
| `update_source_mongo_link(source_id, note_ids)` | Set mongo_note_ids on Source node |

## Related Documentation

- [Memory Overview](./memory.md)
- [Knowledge Graph](./memory-graph.md)
- [Architecture](./architecture.md)
