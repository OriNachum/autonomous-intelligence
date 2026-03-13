# QQ Indexing Architecture Overview

QQ uses a multi-layered indexing system where knowledge flows through extraction, embedding, storage, decay, and archival -- with full provenance tracking at every step.

## Layers at a Glance

| Layer | Storage | What it Indexes | Query Method |
|-------|---------|----------------|--------------|
| **Source/Provenance** | MongoDB + Neo4j | File checksums, git metadata, session IDs | By checksum, source_id |
| **Memory (Notes)** | MongoDB + `notes.md` | Vector-embedded notes with importance scores | Cosine similarity, importance range |
| **Core Notes** | `core.md` file | Protected identity, projects, relationships | Always loaded (no search needed) |
| **Knowledge Graph** | Neo4j | Entities, relationships, embeddings | Cypher traversal, embedding similarity |
| **Context Retrieval** | In-memory `SourceRegistry` | `[N]` citation indices per response | Aggregated from all layers |
| **Archive** | `archive.jsonl` | Decayed/deduplicated notes | Substring search |

## Data Flow

```
User message / File input
        |
        v
  [Extraction Pipeline]
  Entity Agent --> entities (name, type, aliases, confidence)
  Relationship Agent --> relationships (source, target, type, evidence)
  Normalization Agent --> canonical names, alias merging
  Notes Agent --> structured notes by section
        |
        v
  [Embedding Pipeline]
  TEI service (or local sentence-transformers)
  Qwen3-Embedding-0.6B model
        |
        v
  [Storage]
  MongoDB: notes + embeddings + importance + source metadata
  Neo4j: entity nodes + relationship edges + source nodes
  notes.md / core.md: file-based persistence
        |
        v
  [Retrieval & Decay]
  Context Retrieval Agent: vector search + graph traversal
  Importance Scorer: decay over time, boost on access
  Deduplication: cosine similarity consolidation
  Archival: low-importance notes moved to archive.jsonl
```

## Key Source Files

- `src/qq/memory/` -- MongoDB storage, notes files, importance, dedup, archival
- `src/qq/knowledge/neo4j_client.py` -- Neo4j entity/relationship CRUD
- `src/qq/context/retrieval_agent.py` -- RAG context assembly
- `src/qq/services/graph.py` -- Knowledge graph orchestration
- `src/qq/services/analyzer.py` -- File analysis and internalization
- `src/qq/embeddings.py` -- Embedding client (TEI + local fallback)
- `src/qq/memory/source.py` -- SourceRecord provenance tracking
- `src/qq/services/source_registry.py` -- `[N]` citation indexing

## Related Documentation

- [Source & Provenance Indexing](source-provenance.md)
- [Memory Indexing (MongoDB)](memory-mongodb.md)
- [Knowledge Graph Indexing (Neo4j)](knowledge-graph.md)
- [Importance, Decay & Deduplication](importance-decay-dedup.md)
- [Context Retrieval & RAG](context-retrieval.md)
- [File Analysis Pipeline](file-analysis.md)
- [Embedding Pipeline](embeddings.md)
