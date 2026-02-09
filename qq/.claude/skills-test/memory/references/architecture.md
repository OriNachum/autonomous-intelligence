# Architecture Reference

## Memory Flow

```
User Input
    |
    v
+-------------------------------------------+
| Context Retrieval Agent                   |
| 1. Core Notes (always included)          |
| 2. Working Notes (MongoDB vector search) |
| 3. Knowledge Graph (Neo4j entities)      |
+-------------------------------------------+
    |
    v
Context Injection (prepended to system prompt)
    |
    v
LLM Inference -> Assistant Response
    |
    v
+-------------------------------------------+
| Memory Update Pipeline                   |
|------------------------------------------|
| Notes Agent                              |
|   - Analyze conversation history         |
|   - Extract additions/removals           |
|   - Update notes.md + MongoDB            |
|------------------------------------------|
| Knowledge Graph Agent                    |
|   - Extract entities + relationships     |
|   - Normalize against existing graph     |
|   - Store in Neo4j with provenance       |
+-------------------------------------------+
    |
    v
+-------------------------------------------+
| Memory Maintenance (periodic/background) |
| - Importance decay (time-based)          |
| - Deduplication (consolidate similar)    |
| - Archival (low-importance -> archive)   |
| - Promotion (high-importance -> core)    |
+-------------------------------------------+
```

## File Analysis Flow

```
analyze_files(path, focus)
    |
    v
+-------------------------------------------+
| FileAnalyzer                              |
| 1. Read file (text or DocumentReader)     |
| 2. Collect metadata (checksum, git)       |
| 3. Re-analysis detection (MongoDB)        |
| 4. LLM extraction (chunked if large)     |
| 5. Store knowledge:                       |
|    - Notes -> MongoDB + notes.md          |
|    - Entities/Rels -> Neo4j               |
+-------------------------------------------+
```

## Storage Layers

| Layer | Backend | Persistence | Search | Purpose |
|-------|---------|-------------|--------|---------|
| Core Notes | `core.md` file | Permanent | Pattern match | Protected identity/preferences |
| Working Notes | `notes.md` file | Session | Section lookup | Current conversation context |
| MongoDB RAG | MongoDB + embeddings | Persistent | Vector cosine | Long-term recall with semantic search |
| Knowledge Graph | Neo4j | Persistent | Graph traversal + embeddings | Entity relationships and structure |
| Archive | `archive.jsonl` | Persistent | Text search | Forgotten notes (recoverable) |

## Design Decisions

### Single skill, not four

Memory subsystems are tightly coupled:
- `analyze_file` writes to all three stores simultaneously
- `query_similar` needs embeddings from the embedding client
- Deduplication touches both MongoDB and notes.md
- Context retrieval reads from core notes, MongoDB, and Neo4j together

A single skill with grouped references keeps configuration unified.

### Instructions, not SDK

The official skills spec treats skills as "onboarding guides." The existing `qq.memory.*` and `qq.knowledge.*` modules already provide the Python API. The skill tells Claude *how* and *when* to use them.

### config.json alongside env vars

- **Portable**: skill directory can be copied and reconfigured
- **Grouped**: related settings live together (not scattered across .env)
- **Env-var override** still works for deployment/CI

### Wrap existing classes

Existing implementations have proper file locking, atomic writes, error handling, and concurrent access support. The skill references them directly rather than reimplementing.

### Importance decay formula

```
access_bonus = min(0.5, access_count * 0.05)
age_factor = 1.0 / (1 + days_since_creation * 0.01)
staleness = days_since_access * decay_rate
decayed = (importance - staleness + access_bonus) * age_factor
```

Frequently accessed notes resist decay. Old notes decay faster. The formula ensures active knowledge stays relevant while unused knowledge fades.

### Dedup strategy

- Threshold: 0.85 cosine similarity
- Simple merge: keep primary, combine metadata (access counts, dates, sources)
- LLM merge: intelligently combine content, preserving unique info from both
- Source provenance preserved in `source_history` array

### Graceful degradation

Each backend initializes lazily and fails independently. Missing services skip their layer rather than crashing. This enables:
- Development without Docker (file-based notes only)
- Partial deployments (MongoDB only, or Neo4j only)
- Gradual service addition as infrastructure grows
