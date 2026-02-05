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

1. **Pre-Response**: `ContextRetrievalAgent` queries all stores and injects relevant context into the prompt
2. **Response**: The model generates a reply with full context awareness
3. **Post-Response**: Background agents update their respective stores:
   - `NotesAgent` extracts and stores new notes
   - `KnowledgeGraphAgent` extracts entities and relationships
   - High-importance notes may be promoted to core

## Services (docker-compose.yml)

| Service | Port | Purpose |
|---------|------|---------|
| MongoDB | 27017 | Notes storage with vector embeddings |
| Neo4j | 7474/7687 | Knowledge graph (entities + relationships) |
| TEI | 8101 | Text embeddings (Qwen3-Embedding-0.6B) |

## Related Documentation

- [Architecture Overview](./architecture.md)
- [Agents](./agents.md)
- [Sub-agents & Session Isolation](./sub-agents.md)
