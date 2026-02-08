# Memory as Skill — Extraction Plan

**Goal**: Extract QQ's memory subsystems (notes core, notes ephemeral, MongoDB RAG, Neo4j knowledge graph) and `analyze_files` into a standalone, portable **skill** following the [Anthropic skills spec](https://github.com/anthropics/skills). JSON-based service configuration. Includes service initialization with partial setup support and configurable OpenAI-compatible endpoint.

---

## 1. Skill Structure

Following the official Anthropic skill anatomy: `SKILL.md` (required) + `scripts/`, `references/`, `assets/` (optional).

```
skills/memory/
├── SKILL.md                          # Frontmatter + concise workflow guide (<500 lines)
├── config.json                       # Service endpoints & credentials (user-editable)
├── config.sample.json                # Template with defaults
├── scripts/
│   ├── check_services.py             # Health-check all backends
│   ├── start_services.py             # docker-compose up (partial support)
│   ├── setup_openai.py               # Write OpenAI-compat config to config.json
│   └── migrate.py                    # Future: data migration between backends
├── references/
│   ├── notes-core.md                 # Core notes actions + API reference
│   ├── notes-working.md              # Ephemeral/working notes actions
│   ├── mongo-rag.md                  # MongoDB RAG actions + schema
│   ├── neo4j-graph.md                # Neo4j knowledge graph actions + Cypher examples
│   ├── analyze-files.md              # File analysis actions
│   ├── config.md                     # Configuration reference (all fields, env-var overrides)
│   └── architecture.md              # Memory flow diagram, design decisions
└── assets/
    └── docker-compose.yml            # Standalone compose for memory services
```

**Key design choice**: No `actions/` Python package inside the skill. The skill provides *instructions* for Claude to use the existing `qq.memory.*`, `qq.knowledge.*`, and `qq.services.*` modules directly. Scripts are standalone utilities, not an SDK.

---

## 2. SKILL.md — Frontmatter

Only `name` and `description` in frontmatter (per spec). The `description` serves as the primary triggering mechanism — it must be comprehensive about when to use the skill.

```yaml
---
name: memory
description: >
  Unified memory management for notes, knowledge graph, RAG search, and file analysis.
  Use when working with: (1) Core memory — protected identity, projects, relationships,
  and system facts that should never be forgotten, (2) Working notes — per-session
  ephemeral notes organized by section, (3) MongoDB RAG — vector-search-enabled notes
  with importance scoring, decay, deduplication, and archival, (4) Neo4j knowledge
  graph — entities, relationships, merge duplicates, reinforce mentions, Cypher queries,
  (5) File analysis — deep file reading that extracts knowledge into all memory layers,
  (6) Service initialization — health-check, start/stop MongoDB, Neo4j, TEI embeddings
  via docker-compose with partial setup support. Triggers on: memory, notes, remember,
  recall, forget, reinforce, merge entities, knowledge graph, neo4j, mongodb, analyze
  file, archive, restore, embeddings, RAG, vector search, core memory, importance,
  deduplication, initialize services.
---
```

---

## 3. SKILL.md — Body (Progressive Disclosure)

The body stays **lean** (<500 lines). Detailed action references live in `references/`. The body covers:

1. Quick orientation (what memory layers exist)
2. Configuration (point to `config.json`, link to `references/config.md`)
3. High-level workflows per subsystem (3-5 lines each, with links to reference docs)
4. Service initialization quick-start
5. Common patterns / examples

### Draft outline

```markdown
# Memory Skill

Multi-layer memory system: core notes, working notes, MongoDB RAG, Neo4j knowledge graph, and file analysis.

## Configuration

Edit `config.json` in this skill directory. See [config reference](references/config.md) for all fields.

Run `scripts/check_services.py` to verify connectivity. Run `scripts/start_services.py` to launch backends via docker-compose.

For OpenAI API instead of local vLLM: `python scripts/setup_openai.py --base-url https://api.openai.com/v1 --api-key sk-... --model gpt-4o`

## Memory Layers

### Core Notes (protected, never forgotten)

Store identity, projects, relationships, system facts in `memory/core.md`.

```python
from qq.memory.core_notes import CoreNotesManager
mgr = CoreNotesManager()
mgr.add_core("User prefers dark mode", "preferences")
mgr.get_items_by_category("identity")
```

Full API: [references/notes-core.md](references/notes-core.md)

### Working Notes (per-session, ephemeral)

Sectioned notes in `memory/notes.md`. Per-agent isolation via `notes.{id}.md`.

```python
from qq.memory.notes import get_notes_manager
mgr = get_notes_manager("./memory")
mgr.add_item("Key Topics", "QQ memory architecture")
```

Full API: [references/notes-working.md](references/notes-working.md)

### MongoDB RAG (vector search, importance, decay)

Store notes with embeddings. Query by semantic similarity. Importance scoring with time decay.

```python
from qq.memory.mongo_store import MongoNotesStore
store = MongoNotesStore()
store.upsert_note(note_id, content, embedding, section, importance=0.7)
results = store.search_similar(query_embedding, limit=5)
```

Full API + schema: [references/mongo-rag.md](references/mongo-rag.md)

### Neo4j Knowledge Graph (entities, relationships)

Entities as labeled nodes, relationships as edges. Embedding-based search. Source provenance.

```python
from qq.knowledge.neo4j_client import Neo4jClient
client = Neo4jClient()
client.create_entity("Person", "John", {"description": "Engineer"}, embedding)
client.create_relationship("John", "Anthropic", "WORKS_AT")
```

Full API + Cypher examples: [references/neo4j-graph.md](references/neo4j-graph.md)

### File Analysis (extract knowledge from files)

Read file, LLM-extract notes/entities/relationships, store in all layers.

```python
from qq.services.analyzer import FileAnalyzer
analyzer = FileAnalyzer(file_manager)
analyzer.analyze("src/app.py", focus="error handling")
analyzer.analyze_pattern(r"\.py$", "src/", focus="API endpoints")
```

Full API: [references/analyze-files.md](references/analyze-files.md)

## Service Initialization

Services degrade gracefully — each is independently optional.

| Service Down | Effect |
|-------------|--------|
| MongoDB | Notes in `notes.md` only (no vector search) |
| Neo4j | No knowledge graph |
| TEI | No embeddings (notes stored, no similarity search) |
| LLM | No extraction/summarization (manual notes only) |

```bash
python scripts/check_services.py          # status of all services
python scripts/start_services.py          # start all
python scripts/start_services.py mongodb  # start only MongoDB
```

## Architecture

See [references/architecture.md](references/architecture.md) for memory flow diagrams and design decisions.
```

---

## 4. `config.json` — Unified Service Configuration

```json
{
  "llm": {
    "base_url": "http://localhost:8100/v1",
    "api_key": "NO_NEED",
    "model_id": "nvidia/NVIDIA-Nemotron-3-Nano-30B-A3B-FP8"
  },
  "embeddings": {
    "base_url": "http://localhost:8101/v1",
    "model": "Qwen/Qwen3-Embedding-0.6B",
    "prefer_local": false
  },
  "mongodb": {
    "uri": "mongodb://localhost:27017",
    "database": "qq_memory",
    "collection": "notes"
  },
  "neo4j": {
    "uri": "bolt://localhost:7687",
    "user": "neo4j",
    "password": "refinerypass"
  },
  "memory": {
    "memory_dir": "./memory"
  },
  "docker_compose_path": "./docker-compose.yml"
}
```

**Resolution order**: `config.json` > environment variables > hardcoded defaults.

Swap vLLM for OpenAI API by changing `llm.base_url` + `llm.api_key` + `llm.model_id`.

---

## 5. Reference Documents (in `references/`)

Each reference file provides the detailed API that SKILL.md links to. Loaded by Claude only when needed (progressive disclosure).

### 5.1 `references/notes-core.md` — Core Notes

| Action | Signature | Description |
|--------|-----------|-------------|
| `load_notes` | `() -> str` | Load or create core notes |
| `get_notes` | `() -> str` | Get current content |
| `add_core` | `(content, category, source="auto") -> bool` | Add item to protected category |
| `remove_core` | `(pattern, category=None) -> bool` | Remove item by pattern |
| `get_items_by_category` | `(category) -> List[str]` | Get items in a category |
| `get_all_items` | `() -> Dict[str, List[str]]` | All items grouped by category |
| `is_protected` | `(content) -> bool` | Check if content is in core |
| `suggest_promotion` | `(content, importance) -> Optional[str]` | Suggest promoting to core |

Protected categories: Identity, Projects, Relationships, System.

### 5.2 `references/notes-working.md` — Working/Ephemeral Notes

| Action | Signature | Description |
|--------|-----------|-------------|
| `load_notes` | `() -> str` | Load from disk |
| `get_notes` | `() -> str` | Get current content |
| `add_item` | `(section, item) -> bool` | Add item to section |
| `remove_item` | `(section, pattern) -> bool` | Remove by pattern |
| `update_section` | `(section, items) -> None` | Replace entire section |
| `apply_diff` | `(additions, removals) -> None` | Batch add/remove |
| `get_all_items` | `() -> List[dict]` | All items across sections |
| `get_section_items` | `(section) -> List[str]` | Items from one section |
| `count_items` | `() -> int` | Total item count |
| `create_ephemeral` | `(notes_id, initial_context, memory_dir) -> NotesManager` | Create isolated notes |
| `cleanup` | `() -> bool` | Remove ephemeral file |

Sections: Key Topics, Important Facts, People & Entities, Ongoing Threads, File Knowledge.

Factory: `get_notes_manager(memory_dir)` — uses `QQ_NOTES_ID` env var for per-agent isolation.

### 5.3 `references/mongo-rag.md` — MongoDB RAG

**CRUD + Search**:

| Action | Signature | Description |
|--------|-----------|-------------|
| `upsert_note` | `(note_id, content, embedding, section, metadata, importance, decay_rate, source)` | Store/update note |
| `get_note` | `(note_id) -> dict` | Get by ID |
| `get_full_note` | `(note_id) -> dict` | Get with all fields |
| `delete_note` | `(note_id) -> bool` | Delete note |
| `search_similar` | `(query_embedding, limit, section) -> List[dict]` | Cosine similarity search |
| `get_recent_notes` | `(limit, section) -> List[dict]` | By updated_at |
| `clear_all` | `() -> int` | Delete everything |

**Importance & Access**:

| Action | Signature | Description |
|--------|-----------|-------------|
| `increment_access` | `(note_id) -> bool` | Bump access_count + last_accessed |
| `update_importance` | `(note_id, importance) -> bool` | Set importance |
| `bulk_update_importance` | `(updates) -> int` | Batch importance update |
| `get_by_importance_range` | `(min, max, limit) -> List[dict]` | Filter by range |
| `get_stale_notes` | `(days_threshold, limit) -> List[dict]` | Not accessed recently |

**Source Provenance**:

| Action | Signature | Description |
|--------|-----------|-------------|
| `append_source_history` | `(note_id, source, boost_importance) -> bool` | Add source, boost importance |
| `find_by_source_file` | `(file_path, limit) -> List[dict]` | Notes from a file |

**Deduplication** (via `NoteDeduplicator`):

| Action | Signature | Description |
|--------|-----------|-------------|
| `find_similar` | `(threshold, section) -> List[DuplicatePair]` | Find near-duplicates |
| `consolidate` | `(note_a, note_b, use_llm) -> ScoredNote` | Merge two notes |
| `run_consolidation_pass` | `(archive_manager, use_llm) -> ConsolidationReport` | Full dedup pass |

**Importance Scoring** (via `ImportanceScorer`):

| Action | Signature | Description |
|--------|-----------|-------------|
| `score_note` | `(content, section) -> float` | Score 0.0-1.0 |
| `decay_importance` | `(note, current_time) -> float` | Apply time decay |
| `get_archival_candidates` | `(notes, threshold) -> List[ScoredNote]` | Notes to archive |
| `get_promotion_candidates` | `(notes, threshold) -> List[ScoredNote]` | Notes to promote to core |

**Archive** (via `ArchiveManager`):

| Action | Signature | Description |
|--------|-----------|-------------|
| `archive_note` | `(note_id, reason) -> bool` | Archive a note |
| `restore_note` | `(note_id, boost) -> bool` | Restore from archive |
| `search_archive` | `(query, limit) -> List[ArchivedNote]` | Search archived notes |
| `archive_low_importance` | `(threshold) -> int` | Bulk archive low-importance |
| `purge_old_archives` | `(days) -> int` | Delete old archives |

**Document Schema**:

```
note_id, content, embedding, section, metadata, importance (0-1),
decay_rate, access_count, last_accessed, created_at, updated_at,
source {source_type, file_path, checksum, ...}, source_history []
```

### 5.4 `references/neo4j-graph.md` — Neo4j Knowledge Graph

**Entity Operations**:

| Action | Signature | Description |
|--------|-----------|-------------|
| `create_entity` | `(entity_type, name, properties, embedding, aliases, canonical_name, source_id)` | Create node |
| `get_entity` | `(name) -> dict` | Get by name |
| `increment_mention_count` | `(entity_name) -> bool` | Reinforce entity |
| `search_entities_by_embedding` | `(query_embedding, entity_type, limit) -> List[dict]` | Semantic search |
| `get_related_entities` | `(entity_name, depth, limit) -> List[dict]` | Traverse graph |

Entity types: Person, Concept, Topic, Location, Event.

**Relationship Operations**:

| Action | Signature | Description |
|--------|-----------|-------------|
| `create_relationship` | `(source_name, target_name, rel_type, properties) -> bool` | Create edge |

**Source Provenance**:

| Action | Signature | Description |
|--------|-----------|-------------|
| `create_source` | `(source_record) -> str` | Create Source node |
| `link_entity_to_source` | `(entity_name, source_id) -> bool` | EXTRACTED_FROM edge |
| `link_relationship_to_source` | `(source, target, rel_type, source_id) -> bool` | EVIDENCES edge |
| `get_sources_for_entity` | `(entity_name) -> List[dict]` | Get provenance |

**Graph Utilities**:

| Action | Signature | Description |
|--------|-----------|-------------|
| `execute` | `(query, parameters) -> List[dict]` | Raw Cypher |
| `get_graph_summary` | `() -> dict` | Counts by type |

**Merge Entities** (new, to implement):

1. Pick canonical name (provided or most-mentioned)
2. Move all relationships from secondary entities to canonical
3. Merge aliases, descriptions (keep longest), properties
4. Sum mention counts, keep earliest first_seen, latest last_seen
5. Delete secondary entity nodes
6. Update MongoDB notes referencing old entity names

**Common Cypher**:

```cypher
-- Entities by type
MATCH (n) RETURN labels(n)[0] as type, count(n) as count ORDER BY count DESC

-- Orphan entities
MATCH (n) WHERE NOT (n)--() RETURN n.name, labels(n)[0] as type

-- Most connected
MATCH (n)-[r]-() RETURN n.name, count(r) as connections ORDER BY connections DESC LIMIT 10
```

### 5.5 `references/analyze-files.md` — File Analysis

| Action | Signature | Description |
|--------|-----------|-------------|
| `analyze` | `(path, focus="") -> str` | Analyze single file |
| `analyze_pattern` | `(pattern, base_path, focus) -> str` | Batch analyze by regex |

Workflow: read file -> collect metadata (checksum, git) -> re-analysis detection -> LLM extraction (chunked if >30k chars) -> store notes in MongoDB + notes.md -> store entities/relationships in Neo4j -> return summary.

Supported formats: text, PDF, DOCX, XLSX, PPTX.

### 5.6 `references/config.md` — Configuration Reference

All `config.json` fields, env-var override mapping, resolution order, OpenAI API setup instructions.

### 5.7 `references/architecture.md` — Architecture

Memory flow diagram, design decisions (why single skill, why wrap existing classes, importance decay formula, dedup strategy).

---

## 6. Scripts (in `scripts/`)

Standalone utilities, executable directly. Each reads `config.json` from the skill directory.

### `scripts/check_services.py`

```
Usage: python scripts/check_services.py [--config path/to/config.json]

Output:
  mongodb:    ✓ connected (mongodb://localhost:27017)
  neo4j:      ✓ connected (bolt://localhost:7687)
  tei:        ✗ unavailable (http://localhost:8101/v1)
  llm:        ✓ connected (http://localhost:8100/v1)
```

### `scripts/start_services.py`

```
Usage: python scripts/start_services.py [service...]
       python scripts/start_services.py              # start all
       python scripts/start_services.py mongodb neo4j # start subset
```

Runs `docker compose up -d [services]` using the compose file from `config.json`.

### `scripts/setup_openai.py`

```
Usage: python scripts/setup_openai.py --base-url URL --api-key KEY --model MODEL
```

Writes LLM section of `config.json`. Enables the skill to work with any OpenAI-compatible endpoint instead of local vLLM.

---

## 7. Assets

### `assets/docker-compose.yml`

Standalone compose file for memory services (MongoDB, Neo4j, TEI). Copied from project root but self-contained — users can deploy the skill's backends independently.

---

## 8. Implementation Plan

### Phase 1: Scaffolding & Config

1. Create `skills/memory/` directory with `scripts/`, `references/`, `assets/`
2. Write `config.sample.json` with all fields
3. Write `SKILL.md` frontmatter + lean body (<500 lines)
4. Copy `docker-compose.yml` to `assets/`

### Phase 2: Scripts

5. Implement `scripts/check_services.py` — config loader + health checks for all 4 backends
6. Implement `scripts/start_services.py` — docker-compose orchestration with partial support
7. Implement `scripts/setup_openai.py` — config.json writer

### Phase 3: Reference Documents

8. Write `references/notes-core.md` — full API from `CoreNotesManager`
9. Write `references/notes-working.md` — full API from `NotesManager`
10. Write `references/mongo-rag.md` — full API from `MongoNotesStore` + `ImportanceScorer` + `ArchiveManager` + `NoteDeduplicator`
11. Write `references/neo4j-graph.md` — full API from `Neo4jClient` + Cypher examples + merge entities spec
12. Write `references/analyze-files.md` — full API from `FileAnalyzer`
13. Write `references/config.md` — all config fields, env-var mapping
14. Write `references/architecture.md` — flow diagrams, design decisions

### Phase 4: Integration

15. Verify skill loads via qq's `load_all_skills()` and triggers correctly
16. Test with partial service availability (mongo only, neo4j only, all, none)
17. Ensure existing `mongodb-query` and `neo4j-query` agent skills still work (no conflicts)

### Phase 5: Finalize

18. Polish SKILL.md body — ensure <500 lines, all references linked
19. Update project `CLAUDE.md` to mention the memory skill
20. Delete redundant `.agent/skills/mongodb-query/` and `.agent/skills/neo4j-query/` if superseded

---

## 9. Key Design Decisions

### Why instructions, not an SDK?

The official skills spec treats skills as "onboarding guides" — instructions for Claude, not importable libraries. The existing `qq.memory.*` and `qq.knowledge.*` modules already provide the Python API. The skill tells Claude *how* and *when* to use them, with reference docs for the full API surface.

### Why progressive disclosure?

Context window is shared with conversation, system prompt, and other skills. The SKILL.md body gives Claude enough to pick the right subsystem. Reference docs load only when Claude needs the detailed API for a specific operation.

### Why a single skill, not four?

Memory subsystems are tightly coupled: `analyze_file` writes to all three stores, `query_similar` uses embeddings, deduplication touches both MongoDB and notes.md. A single skill with grouped references keeps configuration unified and avoids cross-skill dependencies.

### Why config.json alongside env vars?

- Portable: skill can be copied and reconfigured without touching `.env`
- Grouped: related settings live together (not scattered across env)
- Env-var override still works for deployment/CI

### Partial setup / graceful degradation

Each backend is independently optional. The skill and its scripts detect what's available and adjust behavior. No service = skip that layer, not crash.
