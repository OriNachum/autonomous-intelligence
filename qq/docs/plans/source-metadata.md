# Source Metadata & Provenance Tracking

## Goal

Enrich every item stored in MongoDB (notes) and Neo4j (entities/relationships) with source provenance metadata so that:

1. **Every answer can cite its sources** - "Based on file X, line Y" or "From conversation on date Z"
2. **Content integrity is verifiable** - checksums let us detect if a source file changed since extraction
3. **Source quality is assessable** - git authorship, file origin, conversation context provide trust signals

## Current State

### What exists
- `FileManager.pending_file_reads` tracks `{path, name, content, start_line, end_line, total_lines}` per file read
- History stores file reads with role `"file_content"` including path and line range
- Neo4j relationships have an `evidence` field (free-text quote)
- Entities/relationships track `mention_count`, `first_seen`, `last_seen`

### What's missing
- No `source` field on MongoDB notes or Neo4j entities/relationships
- No file checksums for integrity verification
- No git metadata (author, commit, repo)
- No provenance chain linking extracted knowledge back to specific files or conversations
- Deduplication/archival lose source info when merging

---

## Data Model

### SourceRecord

A reusable structure attached to every stored item:

```python
@dataclass
class SourceRecord:
    # Origin type
    source_type: str          # "file" | "conversation" | "user_input" | "derived"

    # File source (when source_type == "file")
    file_path: Optional[str]  # Absolute path at time of read
    file_name: Optional[str]  # Basename for display
    line_start: Optional[int] # Start line extracted from
    line_end: Optional[int]   # End line extracted from
    checksum: Optional[str]   # SHA-256 of file content at read time

    # Git source (populated if file is in a git repo)
    git_repo: Optional[str]   # Repo root path or remote URL
    git_branch: Optional[str] # Branch name
    git_commit: Optional[str] # Commit hash at read time
    git_author: Optional[str] # Last commit author of the file

    # Conversation source
    session_id: Optional[str] # QQ session ID
    agent_id: Optional[str]   # Agent that extracted this
    timestamp: str            # ISO timestamp of extraction

    # Quality signals
    confidence: Optional[float]  # Extraction confidence (from LLM)
    extraction_model: Optional[str]  # Model ID used for extraction
```

### Storage Format

**MongoDB** - stored as `source` subdocument on each note:
```json
{
  "note_id": "abc123",
  "content": "...",
  "source": {
    "source_type": "file",
    "file_path": "/home/user/project/README.md",
    "file_name": "README.md",
    "line_start": 10,
    "line_end": 25,
    "checksum": "sha256:...",
    "git_repo": "https://github.com/org/repo",
    "git_commit": "a1b2c3d",
    "git_author": "alice",
    "session_id": "sess_123",
    "timestamp": "2025-01-15T10:30:00Z"
  }
}
```

**Neo4j** - stored as properties on entity/relationship nodes:
```cypher
(e:Person {
  name: "Alice",
  source_type: "file",
  source_file: "/path/to/file.md",
  source_checksum: "sha256:...",
  source_git_repo: "https://github.com/org/repo",
  source_git_commit: "a1b2c3d",
  source_git_author: "alice",
  source_session: "sess_123",
  source_timestamp: datetime()
})
```

Neo4j uses flat properties (prefixed with `source_`) rather than nested objects since Neo4j doesn't support nested maps.

---

## Implementation Plan

### Phase 1: Source Collection Infrastructure

**New module: `src/qq/memory/source.py`**

1. Define `SourceRecord` dataclass with `to_dict()` and `from_dict()` serialization
2. Implement `collect_file_source(file_read: dict) -> SourceRecord`:
   - Takes a pending file read dict from FileManager
   - Computes SHA-256 checksum of the full file content
   - Calls `collect_git_metadata(path)` to get git info
   - Returns populated SourceRecord
3. Implement `collect_git_metadata(file_path: str) -> dict`:
   - Runs `git rev-parse --show-toplevel` to find repo root
   - Runs `git log -1 --format='%H %an' -- <file>` for commit + author
   - Runs `git remote get-url origin` for repo URL
   - Runs `git branch --show-current` for branch
   - Returns dict with git fields, or empty dict if not a git repo
   - Cache results per repo root to avoid repeated subprocess calls
4. Implement `collect_conversation_source(session_id, agent_id) -> SourceRecord`:
   - For knowledge extracted from conversation (not file-backed)
5. Implement `validate_checksum(source: SourceRecord) -> bool`:
   - Re-reads the file and compares SHA-256
   - Returns False if file changed or missing

**Files changed:** New file only

### Phase 2: Propagate Source Through Extraction Pipeline

The key insight: source metadata must flow from where files are read (FileManager) through history, into the extraction agents, and finally into storage.

#### 2a. FileManager enrichment

**File: `src/qq/services/file_manager.py`**

- In `read_file()`, after building the file_read dict, compute and attach the checksum and git metadata
- Add `checksum` and `git_*` fields to the pending file read dict
- This is where file content is first seen, so this is the natural place to capture integrity data

#### 2b. History source tracking

**File: `src/qq/app.py`**

- In `_capture_file_reads_to_history()`, preserve the source metadata from file_read dicts
- Store enriched file reads in a session-level registry: `file_sources: dict[str, SourceRecord]` keyed by file path
- This registry is passed to extraction agents so they can look up sources

#### 2c. Notes Agent source propagation

**File: `src/qq/memory/notes_agent.py`**

- `_apply_updates()` receives the file_sources registry
- When upserting to MongoDB, attach the relevant SourceRecord
- For notes derived from conversation (no file), create a conversation-type SourceRecord
- Update the LLM prompt to ask it to indicate which file (if any) each extracted fact came from

#### 2d. Knowledge Graph Agent source propagation

**File: `src/qq/services/graph.py`**

- `_store_extraction()` receives file_sources registry
- When creating entities/relationships, include source properties
- The entity/relationship extraction prompts already process `file_content` messages - extend the extraction schema to ask the LLM to tag each entity with its source file

**Files: `src/qq/agents/entity_agent/`, `src/qq/agents/relationship_agent/`**

- Update extraction prompts (`.system.md`) to include a `source_file` field in the output schema
- The LLM should indicate which file (or "conversation") each entity/relationship was extracted from

### Phase 3: Storage Layer Changes

#### 3a. MongoDB schema update

**File: `src/qq/memory/mongo_store.py`**

- Add `source: Optional[Dict]` parameter to `upsert_note()`
- Store as subdocument
- Add index on `source.file_path` for file-based lookups
- Add index on `source.source_type` for filtering
- On update (existing note), append to a `source_history` array to track multiple sources confirming the same fact

#### 3b. Neo4j Source entity (datasource-as-node)

Instead of scattering `source_*` flat properties across every entity, model the datasource as a first-class **Source node** in Neo4j. This node is *not* extracted by the LLM from conversation content - it represents the datasource itself and is created programmatically whenever a file is read or a conversation produces knowledge.

**Schema:**

```cypher
(:Source {
  source_id: "sha256:<checksum>",     -- unique ID (checksum for files, session_id for conversations)
  source_type: "file" | "conversation" | "user_input",
  file_path: "/absolute/path/to/file.md",
  file_name: "file.md",
  checksum: "sha256:...",
  git_repo: "https://github.com/org/repo",
  git_branch: "main",
  git_commit: "a1b2c3d",
  git_author: "alice",
  session_id: "sess_123",
  agent_id: "default",
  mongo_source_id: "note_abc123",     -- foreign key to MongoDB source subdocument
  created_at: datetime(),
  last_verified: datetime(),
  verified: true                       -- checksum still valid
})
```

**Relationships to extracted entities:**

```cypher
(entity:Person)-[:EXTRACTED_FROM]->(source:Source)
(entity:Concept)-[:EXTRACTED_FROM]->(source:Source)
(source:Source)-[:STORED_IN {collection: "notes", note_ids: ["abc", "def"]}]->(ref:MongoRef)
```

Every extracted entity and relationship gets an `EXTRACTED_FROM` edge back to its Source node. This means:
- Traversing from any entity to its source is a single hop: `MATCH (e)-[:EXTRACTED_FROM]->(s:Source) WHERE e.name = "Alice" RETURN s`
- Finding all knowledge from a specific file: `MATCH (s:Source {file_path: "/path/to/file"})<-[:EXTRACTED_FROM]-(e) RETURN e`
- Cross-referencing with MongoDB: the `mongo_source_id` field links to the `source` subdocument on MongoDB notes, enabling full round-trip from graph entity → Source node → MongoDB note with full content

**Implementation in `src/qq/knowledge/neo4j_client.py`:**

- Add `create_source(source_record: dict) -> str` method:
  - MERGE on `source_id` (idempotent - same file/checksum reuses the node)
  - Returns the `source_id` for linking
- Add `link_entity_to_source(entity_name: str, source_id: str)` method:
  - Creates `(entity)-[:EXTRACTED_FROM]->(source)` edge
- Add `link_relationship_to_source(source_name: str, target_name: str, rel_type: str, source_id: str)` method:
  - Finds the relationship and creates an intermediate connection to the Source node
  - Since Neo4j can't have edges-to-edges, create: `(source:Source)-[:EVIDENCES {rel_type, source_name, target_name}]->(target_entity)`
- Add `update_source_verification(source_id: str, verified: bool)` for checksum re-validation
- Add `get_sources_for_entity(entity_name: str) -> List[dict]` query helper

**Implementation in `src/qq/services/graph.py`:**

- In `_store_extraction()`, before creating entities:
  1. Build a SourceRecord from the file_sources registry
  2. Call `neo4j.create_source(source_record)` to get/create the Source node
  3. After each `create_entity()`, call `link_entity_to_source(name, source_id)`
  4. After each `create_relationship()`, call `link_relationship_to_source(..., source_id)`
  5. Store the MongoDB note_ids on the Source node via `mongo_source_id` to close the loop

**MongoDB ↔ Neo4j link:**

The `source` subdocument in MongoDB and the `Source` node in Neo4j share the same `source_id` (derived from checksum for files, session_id for conversations). This enables:
- From MongoDB note → lookup `source.source_id` → query Neo4j for the Source node and all linked entities
- From Neo4j entity → traverse `EXTRACTED_FROM` → Source node → read `mongo_source_id` → fetch full note content from MongoDB

#### 3c. Neo4j entity/relationship source properties (lightweight fallback)

**File: `src/qq/knowledge/neo4j_client.py`**

- Still add `source_id` as a flat property on entities/relationships as a quick-access denormalization
- On MERGE (existing entity), keep `source_first_id` from first creation and update `source_latest_id`
- The full source details live on the Source node; the flat property is just a pointer for fast queries without traversal

#### 3e. Deduplication source preservation

**File: `src/qq/memory/deduplication.py`**

- When merging duplicate notes, combine source records into a `sources` array (multiple sources strengthen a fact)
- Keep the earliest source as `primary_source`

#### 3f. Archive source preservation

**File: `src/qq/memory/archive.py`**

- Include source metadata in archived note records

### Phase 4: Source-Aware Context Retrieval

**File: `src/qq/context/retrieval_agent.py`**

- When formatting context for injection, include source citations:
  ```
  **Relevant Memory Notes:**
  - User prefers dark mode [source: conversation, 2025-01-10]
  - Project uses React 19 [source: package.json, verified ✓]
  ```
- Add `_format_source_citation(source: dict) -> str` helper
- Include checksum validation status (verified/stale/missing) as a trust indicator

### Phase 5: Source Validation & Quality

**New module: `src/qq/memory/source_validation.py`**

1. `validate_sources(mongo_store) -> ValidationReport`:
   - Iterate notes with file sources
   - Re-check checksums
   - Flag stale sources (file changed since extraction)
   - Flag missing sources (file deleted)
2. `get_source_quality(source: dict) -> float`:
   - Score based on: has git author (+0.2), has checksum (+0.2), checksum valid (+0.3), has file path (+0.2), recent (+0.1)
3. Integrate with importance scoring in `src/qq/memory/importance.py`:
   - Notes with verified sources get importance boost
   - Notes with stale/missing sources get decay penalty

---

## File Change Summary

| File | Change Type | Description |
|------|-------------|-------------|
| `src/qq/memory/source.py` | **New** | SourceRecord dataclass, git metadata collection, checksum utils |
| `src/qq/memory/source_validation.py` | **New** | Validation, quality scoring |
| `src/qq/services/file_manager.py` | Modify | Compute checksum + git metadata on file read |
| `src/qq/app.py` | Modify | Track file sources through session, pass to agents |
| `src/qq/memory/notes_agent.py` | Modify | Accept + store source metadata with notes |
| `src/qq/memory/mongo_store.py` | Modify | Add `source` field to schema, new indexes |
| `src/qq/knowledge/neo4j_client.py` | Modify | Add Source node CRUD, `EXTRACTED_FROM` linking, `source_id` on entities |
| `src/qq/services/graph.py` | Modify | Create Source nodes, link entities/relationships to sources, bridge to MongoDB |
| `src/qq/agents/entity_agent/*.system.md` | Modify | Add `source_file` to extraction schema |
| `src/qq/agents/relationship_agent/*.system.md` | Modify | Add `source_file` to extraction schema |
| `src/qq/context/retrieval_agent.py` | Modify | Include source citations in context output |
| `src/qq/memory/deduplication.py` | Modify | Preserve/merge sources on dedup |
| `src/qq/memory/archive.py` | Modify | Include source in archive records |
| `src/qq/memory/importance.py` | Modify | Source quality affects importance score |

## Migration

- Existing notes/entities without source metadata continue to work (all source fields are optional)
- A one-time backfill script can scan notes with content matching known files and retroactively attach sources
- No schema migration needed for MongoDB (schemaless) or Neo4j (property graph)

## Phasing Recommendation

**Phase 1 + 2 + 3** are the core and should be done together - source collection is useless without storage, and storage is useless without collection. This is the MVP.

**Phase 4** (citations in retrieval) provides the user-facing value - answers cite their sources. Do this immediately after the core.

**Phase 5** (validation & quality) is a quality-of-life enhancement that makes the system self-healing. Can be done later.
