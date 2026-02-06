# Memory Agent Tools Plan

Give agents direct, intentional control over their memory through four tools: `memory_add`, `memory_verify`, `memory_query`, and `memory_reinforce`.

## What Already Exists

### Memory Storage (passive, agent-invisible)
- **MongoNotesStore** (`memory/mongo_store.py`): Vector-indexed notes with embeddings, importance scores, source provenance, access tracking
- **NotesManager** (`memory/notes.py`): File-based `notes.md` with section structure (Key Topics, Important Facts, People & Entities, etc.), session-isolated ephemeral notes
- **CoreNotesManager** (`memory/core_notes.py`): Protected never-forgotten memory (identity, projects, relationships, system)
- **ImportanceScorer** (`memory/importance.py`): Content+access scoring with time decay, archival/promotion thresholds
- **NoteDeduplicator** (`memory/deduplication.py`): Embedding-based duplicate detection and consolidation
- **ArchiveManager** (`memory/archive.py`): Low-importance note forgetting with restore capability

### Knowledge Graph (passive, agent-invisible)
- **Neo4jClient** (`knowledge/neo4j_client.py`): Entity/relationship storage with embeddings, source provenance (Source nodes, EXTRACTED_FROM/EVIDENCES edges)

### Context Retrieval (read-only, automatic)
- **ContextRetrievalAgent** (`context/retrieval_agent.py`): Injects core notes + vector-similar notes + related entities into system prompt before each turn. Agents **cannot** control what gets retrieved or stored.

### Source Provenance
- **SourceRecord** (`memory/source.py`): Tracks file/conversation/git metadata for all stored knowledge

### Current Gap
Agents have **zero direct interaction** with memory. The notes agent (`memory/notes_agent.py`) runs post-conversation to extract notes via LLM, and context retrieval injects relevant notes pre-turn. But agents cannot:
- Intentionally store something they've learned
- Check if something they know is already recorded or conflicts
- Search their memory for specific information
- Strengthen existing knowledge when new evidence appears

## Tool Designs

### Tool Registration

All four tools are registered in `_create_common_tools()` in `agents/__init__.py`, following the existing `@tool` pattern. They share initialized instances of `MongoNotesStore`, `NotesManager`, `CoreNotesManager`, `EmbeddingClient`, and `ImportanceScorer`.

A new helper `_create_memory_tools()` keeps the tools grouped and returns a list, same pattern as the existing common tools. `load_agent()` and `_create_default_agent()` call it and extend `agent_tools`.

### Initialization

```python
# In _create_memory_tools() or at load_agent scope
embedding_client = EmbeddingClient()
mongo_store = MongoNotesStore(embedding_client)
notes_manager = NotesManager(memory_dir)
core_notes = CoreNotesManager(memory_dir)
importance_scorer = ImportanceScorer()
```

Connection setup is lazy (MongoNotesStore connects on first call, EmbeddingClient selects backend on first embed). No new startup cost.

---

### 1. `memory_add`

**Purpose**: Intentionally store a piece of knowledge the agent has learned or been told.

```python
@tool
def memory_add(content: str, section: str = "Important Facts", importance: str = "normal") -> str:
    """
    Store information in long-term memory.

    Use this when you learn something worth remembering across conversations:
    new facts, user preferences, project details, decisions made, or
    conclusions drawn from analysis.

    Args:
        content: The information to remember. Be specific and self-contained.
        section: Category - one of: Key Topics, Important Facts,
                 People & Entities, Ongoing Threads, File Knowledge.
        importance: Priority level - "low", "normal", "high", or "core".
                    Use "core" only for user identity, key relationships,
                    or critical project info that should never be forgotten.
    """
```

**Implementation**:
1. Generate embedding via `EmbeddingClient`
2. Check for near-duplicates via `MongoNotesStore.search_similar()` (threshold 0.85) — if found, delegate to `memory_reinforce` logic instead and return a message saying "reinforced existing note" with the match
3. Map importance string to float: low=0.3, normal=0.5, high=0.7, core=0.9
4. Collect source metadata from `file_manager.get_pending_file_reads()` or conversation context
5. Store in MongoDB via `mongo_store.upsert_note()`
6. Add to `notes.md` via `notes_manager.add_item(section, content)`
7. If importance == "core", also add via `core_notes.add_core()`
8. Return confirmation with note_id and whether it was new or reinforced

---

### 2. `memory_query`

**Purpose**: Search memory for specific information, beyond what automatic context retrieval provides.

```python
@tool
def memory_query(query: str, scope: str = "all", limit: int = 5) -> str:
    """
    Search your memory for specific information.

    Use this when you need to recall something specific that may not have
    been included in your automatic context, or to check what you know
    about a topic before responding.

    Args:
        query: What to search for. Can be a topic, question, or keywords.
        scope: Where to search - "notes" (working memory), "knowledge"
               (entity graph), "archive" (forgotten notes), or "all".
        limit: Maximum results to return (default 5).
    """
```

**Implementation**:
1. Generate embedding for query
2. Based on scope:
   - `notes`: `mongo_store.search_similar(embedding, limit)` — return content, importance, last_accessed, source summary
   - `knowledge`: `neo4j_client.search_entities_by_embedding(embedding, limit)` + `get_related_entities()` for top hit — return entities with relationships
   - `archive`: `archive_manager.search_archive(query)` — return archived notes with archive reason/date
   - `all`: Run notes + knowledge in sequence, merge results sorted by relevance score
3. Format results as structured text with relevance scores
4. Track access via `mongo_store.increment_access()` for retrieved notes
5. Return formatted results or "No matching memories found"

---

### 3. `memory_verify`

**Purpose**: Check if a piece of information is already known, and whether it conflicts with or confirms existing knowledge.

```python
@tool
def memory_verify(claim: str) -> str:
    """
    Verify a claim against existing memory.

    Use this before storing new information to check for conflicts,
    or when you want to validate something you've been told against
    what you already know.

    Args:
        claim: A statement to verify against existing memory.
               Be specific — e.g., "The database runs on port 5432"
               rather than "database port".
    """
```

**Implementation**:
1. Generate embedding for claim
2. Search MongoDB for similar notes (threshold 0.6 — lower than dedup, to catch related-but-different)
3. Search Neo4j for related entities
4. For each match above threshold, classify relationship:
   - **Confirms** (similarity > 0.85): "This is already known" — show existing note with source
   - **Related** (0.6 < similarity < 0.85): "Related information exists" — show notes that may support or contextualize
   - **No match** (similarity < 0.6): "No existing knowledge about this"
5. If related notes exist, check for contradiction signals:
   - Same entities but different values (heuristic: shared proper nouns but low overall similarity)
   - Flag as "Potential conflict — review recommended" with both the claim and existing note
6. Return structured report: status (confirmed/related/new/conflict), matching notes with sources, confidence

---

### 4. `memory_reinforce`

**Purpose**: When a known fact is encountered again from a new or different source, strengthen it.

```python
@tool
def memory_reinforce(content: str, new_evidence: str = "") -> str:
    """
    Reinforce existing memory with additional evidence or a new source.

    Use this when you encounter information that confirms something
    already in memory, especially from a different source. This increases
    the information's importance and records the additional provenance.

    Args:
        content: The information to reinforce (will be matched against
                 existing memory by similarity).
        new_evidence: Optional additional context, quote, or source
                      description that supports the existing memory.
    """
```

**Implementation**:
1. Generate embedding for content
2. Find best match in MongoDB via `search_similar()` (threshold 0.75)
3. If no match found, return "No matching memory found to reinforce. Use memory_add to store new information."
4. For the matched note:
   a. Boost importance: `new_importance = min(existing + 0.1, 1.0)` via `mongo_store.update_importance()`
   b. Increment access count via `mongo_store.increment_access()`
   c. Collect current source metadata
   d. Append to `source_history` array in MongoDB (provenance chain)
   e. If `new_evidence` provided, append to note content or store as annotation
   f. If boosted importance crosses core threshold (0.8), suggest promotion to core notes
5. If the note is a Neo4j entity, also increment `mention_count` and update `last_seen`
6. Return confirmation: what was reinforced, old→new importance, source count, promotion suggestion if applicable

---

## File Changes

| File | Change |
|------|--------|
| `src/qq/agents/__init__.py` | Add `_create_memory_tools()`, call from `load_agent()` and `_create_default_agent()`, add imports |
| `src/qq/memory/mongo_store.py` | Add `append_source_history()` method if not already supported by upsert |
| `src/qq/knowledge/neo4j_client.py` | Add `increment_mention_count(entity_name)` if not present |
| New: `src/qq/services/memory_tools.py` | (Optional) If `_create_memory_tools()` grows large, extract to its own module following the `file_manager`/`child_process` pattern |

## Dependencies

No new dependencies. All required components exist:
- `strands` (Agent, tool) — already used
- `MongoNotesStore`, `NotesManager`, `CoreNotesManager` — existing
- `EmbeddingClient` — existing
- `ImportanceScorer` — existing
- `ArchiveManager` — existing
- `Neo4jClient` — existing
- `SourceRecord` — existing

## Initialization Concerns

- **Lazy connections**: MongoDB and Neo4j connect on first use, so tools that aren't called don't impose startup cost
- **Embedding availability**: If TEI is down, tools should gracefully degrade (store without embeddings, search by text match)
- **Session isolation**: Memory tools operate on shared memory (not session-isolated), which is intentional — memory should persist across sessions
- **Parallel safety**: MongoNotesStore uses MongoDB's atomic operations; NotesManager uses file locking. Both are safe for concurrent access.
