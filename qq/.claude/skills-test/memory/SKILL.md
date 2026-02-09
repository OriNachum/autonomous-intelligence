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
  via docker-compose with partial setup support.
triggers:
  - memory
  - notes
  - remember
  - recall
  - forget
  - reinforce
  - merge entities
  - knowledge graph
  - neo4j
  - mongodb
  - mongo
  - analyze
  - archive
  - restore
  - embeddings
  - vector search
  - core memory
  - importance
  - deduplication
---

# Memory Skill

Multi-layer memory system: core notes, working notes, MongoDB RAG, Neo4j knowledge graph, and file analysis.

## Configuration

Edit `config.json` in this skill directory. See [config reference](references/config.md) for all fields and env-var overrides.

```bash
python scripts/check_services.py          # verify connectivity
python scripts/start_services.py          # launch all backends
python scripts/start_services.py mongodb  # launch subset
```

For OpenAI API instead of local vLLM:

```bash
python scripts/setup_openai.py --base-url https://api.openai.com/v1 --api-key sk-... --model gpt-4o
```

## Memory Layers

### Core Notes (protected, never forgotten)

Store identity, projects, relationships, system facts in `memory/core.md`. These survive all memory maintenance operations.

```python
from qq.memory.core_notes import CoreNotesManager

mgr = CoreNotesManager()
mgr.add_core("User prefers dark mode", "preferences")
mgr.get_items_by_category("identity")
mgr.get_all_items()  # {category: [items]}
mgr.remove_core("dark mode", "preferences")
mgr.is_protected("User prefers dark mode")  # True if in core
```

Protected categories: `identity`, `projects`, `relationships`, `system`.

Full API: [references/notes-core.md](references/notes-core.md)

### Working Notes (per-session, ephemeral)

Sectioned notes in `memory/notes.md`. Per-agent isolation via `notes.{id}.md`.

```python
from qq.memory.notes import get_notes_manager

mgr = get_notes_manager("./memory")
mgr.add_item("Key Topics", "QQ memory architecture")
mgr.get_section_items("Key Topics")
mgr.remove_item("Key Topics", "QQ memory")
mgr.apply_diff(
    additions=[{"section": "Important Facts", "item": "New fact"}],
    removals=["Old fact"]
)
```

Sections: `Key Topics`, `Important Facts`, `People & Entities`, `Ongoing Threads`, `File Knowledge`.

Full API: [references/notes-working.md](references/notes-working.md)

### MongoDB RAG (vector search, importance, decay)

Store notes with embeddings. Query by semantic similarity. Importance scoring with time-based decay, deduplication, and archival.

```python
from qq.memory.mongo_store import MongoNotesStore
from qq.embeddings import EmbeddingClient

embeddings = EmbeddingClient()
store = MongoNotesStore()

# Store
embedding = embeddings.get_embedding("QQ uses MongoDB for notes")
store.upsert_note("note_abc", "QQ uses MongoDB for notes", embedding, "Key Topics", importance=0.7)

# Search
query_emb = embeddings.get_embedding("what database does QQ use?")
results = store.search_similar(query_emb, limit=5)

# Reinforce
store.increment_access("note_abc")
store.append_source_history("note_abc", {"source_type": "conversation"}, boost_importance=0.1)

# Maintenance
store.get_stale_notes(days_threshold=30)
store.get_by_importance_range(min_importance=0.0, max_importance=0.1)
```

Full API + schema + dedup + archive: [references/mongo-rag.md](references/mongo-rag.md)

### Neo4j Knowledge Graph (entities, relationships)

Entities as labeled nodes, relationships as edges. Embedding-based semantic search. Source provenance tracking.

```python
from qq.knowledge.neo4j_client import Neo4jClient
from qq.embeddings import EmbeddingClient

embeddings = EmbeddingClient()
client = Neo4jClient()

# Create entities
emb = embeddings.get_embedding("John, software engineer")
client.create_entity("Person", "John", {"description": "Software engineer"}, emb)

# Create relationships
client.create_relationship("John", "Anthropic", "WORKS_AT", {"role": "Engineer"})

# Query
client.get_entity("John")
client.get_related_entities("John", depth=2, limit=20)
client.search_entities_by_embedding(query_emb, entity_type="Person", limit=10)

# Reinforce
client.increment_mention_count("John")

# Raw Cypher
client.execute("MATCH (n:Person) RETURN n.name, n.description LIMIT 10")
client.get_graph_summary()
```

Full API + Cypher examples + merge spec: [references/neo4j-graph.md](references/neo4j-graph.md)

### File Analysis (extract knowledge from files)

Read a file, LLM-extract notes/entities/relationships, store in all memory layers.

```python
from qq.services.analyzer import FileAnalyzer

analyzer = FileAnalyzer(file_manager)
analyzer.analyze("src/app.py", focus="error handling")
analyzer.analyze_pattern(r"\.py$", "src/", focus="API endpoints")
```

Supports: text, PDF, DOCX, XLSX, PPTX. Chunks large files automatically. Detects re-analysis via checksum.

Full API: [references/analyze-files.md](references/analyze-files.md)

## Service Initialization

Each backend is independently optional. The system degrades gracefully:

| Service Down | Effect |
|-------------|--------|
| MongoDB | Notes in `notes.md` only (no vector search) |
| Neo4j | No knowledge graph (entities/relationships skipped) |
| TEI | No embeddings (notes stored, no similarity search) |
| LLM | No extraction/summarization (manual notes only) |

```bash
python scripts/check_services.py                # status of all
python scripts/start_services.py                 # start all
python scripts/start_services.py mongodb neo4j   # start subset
python scripts/start_services.py --stop          # stop all
python scripts/start_services.py --stop tei      # stop subset
```

Use `assets/docker-compose.yml` for standalone deployment of memory backends.

## Common Workflows

### Store and recall a fact

```python
from qq.memory.core_notes import CoreNotesManager
from qq.memory.mongo_store import MongoNotesStore
from qq.embeddings import EmbeddingClient

# Store in core (protected)
core = CoreNotesManager()
core.add_core("User's name is Alice", "identity")

# Store in MongoDB (searchable)
emb_client = EmbeddingClient()
store = MongoNotesStore()
embedding = emb_client.get_embedding("User's name is Alice")
store.upsert_note("note_name", "User's name is Alice", embedding, "People & Entities", importance=0.9)
```

### Analyze a file and query results

```python
# Analyze
analyzer.analyze("README.md", focus="project overview")

# Query what was learned
results = store.search_similar(emb_client.get_embedding("project overview"), limit=5)
entities = client.search_entities_by_embedding(emb_client.get_embedding("project"), limit=5)
```

### Merge duplicate entities

```python
# Find duplicates via Cypher
dupes = client.execute("""
    MATCH (a:Person), (b:Person)
    WHERE a.name < b.name AND a.canonical_name = b.canonical_name
    RETURN a.name, b.name
""")

# Manual merge (move relationships, combine properties, delete secondary)
# See references/neo4j-graph.md for merge_entities procedure
```

### Memory maintenance

```python
from qq.memory.importance import ImportanceScorer
from qq.memory.archive import ArchiveManager
from qq.memory.deduplication import NoteDeduplicator

scorer = ImportanceScorer()
archive = ArchiveManager("./memory")
dedup = NoteDeduplicator(store, emb_client)

# Decay importance over time
notes = store.get_recent_notes(limit=100)
# ... apply scorer.decay_importance() and store.update_importance()

# Archive low-importance notes
archive.archive_low_importance(threshold=0.05)

# Deduplicate
dedup.run_consolidation_pass(archive)
```

## Architecture

See [references/architecture.md](references/architecture.md) for memory flow diagrams and design decisions.
