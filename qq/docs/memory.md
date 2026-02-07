# QQ Memory Architecture

The `qq` agent employs a multi-layered memory architecture designed to maintain long-term context, structure knowledge, and provide relevant information during interactions.

> **Note**: Each QQ session (including sub-agent child processes) maintains isolated memory state. See [sub-agents.md](./sub-agents.md) for details on session isolation.

## Memory Components

| Component | Storage | Purpose | Documentation |
|-----------|---------|---------|---------------|
| **Knowledge Graph** | Neo4j | Structured entities & relationships | [memory-graph.md](./memory-graph.md) |
| **Flat Notes (RAG)** | MongoDB | Vector-searchable notes | [memory-flat.md](./memory-flat.md) |
| **Core Notes** | File (`core.md`) | Protected essential information | [memory-notes-core.md](./memory-notes-core.md) |
| **Ephemeral Notes** | File (`notes.*.md`) | Per-agent working memory | [memory-notes-ephemeral.md](./memory-notes-ephemeral.md) |

## Architecture Diagram

```
                    ┌─────────────────────────────────────────┐
                    │           User Query                     │
                    └─────────────────┬───────────────────────┘
                                      │
                    ┌─────────────────▼───────────────────────┐
                    │       ContextRetrievalAgent              │
                    │   (src/qq/context/retrieval_agent.py)    │
                    └─────────────────┬───────────────────────┘
                                      │
              ┌───────────────────────┼───────────────────────┐
              │                       │                       │
    ┌─────────▼─────────┐   ┌────────▼────────┐   ┌─────────▼─────────┐
    │   MongoDB RAG     │   │   Neo4j Graph   │   │   File Notes      │
    │  (Vector Search)  │   │ (Entity Search) │   │  (Core/Ephemeral) │
    └─────────┬─────────┘   └────────┬────────┘   └─────────┬─────────┘
              │                       │                       │
              └───────────────────────┼───────────────────────┘
                                      │
                    ┌─────────────────▼───────────────────────┐
                    │        Context Injection                 │
                    │     (Into System Prompt)                 │
                    └─────────────────┬───────────────────────┘
                                      │
                    ┌─────────────────▼───────────────────────┐
                    │           LLM Response                   │
                    └─────────────────┬───────────────────────┘
                                      │
              ┌───────────────────────┼───────────────────────┐
              │                       │                       │
    ┌─────────▼─────────┐   ┌────────▼────────┐   ┌─────────▼─────────┐
    │    NotesAgent     │   │ KnowledgeGraph  │   │   Core Notes      │
    │  (Background)     │   │    Agent        │   │   Promotion       │
    └───────────────────┘   └─────────────────┘   └───────────────────┘
```

## Integration Cycle

All memory components are initialized in the main application entry point (`src/qq/app.py`):

1. **Pre-Response**: `ContextRetrievalAgent` queries all stores and injects relevant context into the prompt. Each retrieved item is assigned a `[N]` source index for citation tracking.
2. **Response**: The model generates a reply with full context awareness, using `[N]` markers to cite sources.
3. **Explicit Memory Writes**: Memory is only stored via explicit tool calls — no automatic post-turn extraction:
   - `memory_add` — Store new information with category and importance
   - `memory_reinforce` — Strengthen existing knowledge with new evidence
   - `memory_verify` — Check for conflicts before storing
   - `analyze_file` — Deep file internalization into all memory layers
4. **Post-Response**: Alignment agent verifies citation accuracy. Source footer appended to response.

### Shared vs. Isolated Memory

| Component | Root Agent | Sub-Agents | Notes |
|-----------|-----------|------------|-------|
| Core Notes (`core.md`) | Read/Write | Read-only | Identity, projects — shared across all |
| Working Notes (`notes.md`) | Read/Write | Isolated (`notes.{id}.md`) | Each child gets ephemeral copy |
| MongoDB (RAG) | Full access | Full access | Shared store, but writes are task-scoped |
| Neo4j (Graph) | Full access | Full access | Shared graph database |

### Source Provenance

Every memory item tracks its origin via `SourceRecord` (`src/qq/memory/source.py`):
- SHA-256 checksums for file content verification
- Git metadata (repo, branch, commit, author)
- Session and agent IDs
- Audit trail via `source_history` array

See [source-metadata.md](./source-metadata.md) for full details.

## Services (docker-compose.yml)

| Service | Port | Purpose |
|---------|------|---------|
| MongoDB | 27017 | Notes storage with vector embeddings |
| Neo4j | 7474/7687 | Knowledge graph (entities + relationships) |
| TEI | 8101 | Text embeddings (Qwen3-Embedding-0.6B) |

## Related Documentation

- [Architecture Overview](./architecture.md)
- [Agents](./agents.md): All 8 agents including memory-related agents
- [Sub-agents & Session Isolation](./sub-agents.md): Ephemeral notes and shared memory
- [Source Metadata](./source-metadata.md): Provenance tracking for memory items
- [Citation & Alignment](./anchoring-answers-in-sources.md): How memory feeds into citations
- [File Analyzer](./analyzer-agent.md): Deep file internalization into memory
