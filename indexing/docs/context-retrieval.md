# Context Retrieval & RAG

Before each response, the `ContextRetrievalAgent` assembles relevant context from all memory layers and injects it into the system prompt with `[N]` citation markers.

## Retrieval Flow

Defined in `src/qq/context/retrieval_agent.py:102-286`.

### `prepare_context()` (`retrieval_agent.py:102-166`)

1. **Core notes** (always included) -- `core_manager.get_all_items()` returns Identity, Projects, Relationships, System
2. **Working notes** (vector search) -- top 3 most relevant via embedding similarity
3. **Knowledge graph entities** (embedding search) -- top 5 most relevant entities from Neo4j
4. Format everything into a context block with `[N]` indices

### Core Notes Retrieval (`retrieval_agent.py:128-132`)

- Always loaded, no filtering
- Provides stable identity and context across all conversations
- Categories: Identity, Projects, Relationships, System

### Working Notes Retrieval (`retrieval_agent.py:135-144`)

- `notes_agent.get_relevant_notes(query, limit=3)`
- Embedding-based vector similarity search against MongoDB
- Access tracking via `increment_access()` (feeds importance decay)
- Falls back to recent notes if embeddings are unavailable

### Entity Retrieval (`retrieval_agent.py:147-154`)

- `knowledge_agent.get_relevant_entities(query, limit=5)`
- Embedding similarity search on Neo4j entity nodes
- Returns entities with similarity scores

## Context Formatting

### `_format_context()` (`retrieval_agent.py:186-286`)

Builds a structured text block:

```
## Retrieved Context

### Core Memory (User Profile)
[1] Identity: ...
[2] Projects: ...

### Relevant Memory Notes
[3] note content (importance: 0.7)
[4] note content (importance: 0.5)

### Related Knowledge
[5] Entity: Person - description
[6] Entity: Concept - description
```

Each item gets a `[N]` index via `source_registry.add(type, label, detail)`.

Items below `CITE_THRESHOLD` (0.3) are filtered out.

### System Prompt Injection (`retrieval_agent.py:288-324`)

- Prepends `## Retrieved Context` section to system prompt
- Includes explanation of `[N]` indices for the LLM
- Separated from main prompt with `---`

## Notes Agent (Summarization & Search)

Defined in `src/qq/memory/notes_agent.py:52-316`.

### `process_messages()` (`notes_agent.py:154-219`)

1. Load current `notes.md` content
2. Format last 20 messages
3. LLM analyzes via `NOTES_EXTRACTION_PROMPT`
4. Returns JSON: `{"additions": [...], "removals": [...], "summary": "..."}`

### `_apply_updates()` (`notes_agent.py:221-288`)

1. Update `notes.md` file via `apply_diff()`
2. Generate embeddings for new items
3. Store in MongoDB with source provenance
4. Note IDs: `SHA256(content)[:16]`

### Vector Search (`notes_agent.py:290-312`)

`get_relevant_notes()`: Query embedding --> MongoDB similarity search --> top-k with scores. Falls back to recent notes if embeddings are unavailable.

## Alignment Agent (Post-Answer Citation Verification)

Defined in `src/qq/services/alignment.py`.

After the LLM generates a response:
1. Silent review of `[N]` citations against actual source content
2. Flags unsupported claims
3. Runs only when `QQ_ALIGNMENT_ENABLED=true`
