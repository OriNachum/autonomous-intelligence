# Memory Anchoring & Answer Alignment Plan

Three changes: make memory intentional (not passive), require source citations on every answer, and add a silent post-answer alignment review.

---

## 1. Remove Passive Memory Extraction

**Problem**: The `NotesAgent.process_messages()` runs after every turn in `app.py`, automatically extracting facts from conversation into notes.md and MongoDB. This means agents store things the user never asked to remember, cluttering memory with noise.

**Change**: Remove the passive post-turn `notes_agent.process_messages()` and `knowledge_agent.process_messages()` calls. Memory storage happens **only** through explicit `memory_add` tool calls by the agent.

### Files to Change

**`src/qq/app.py`** — Remove post-turn memory extraction in both `run_cli_mode()` and `run_console_mode()`:

```python
# REMOVE these blocks (appear in both modes, after history.add):
#     messages = history.get_messages()
#     if notes_agent:
#         notes_agent.process_messages(messages)
#     if knowledge_agent:
#         knowledge_agent.process_messages(messages)
```

The `notes_agent` and `knowledge_agent` instances are still initialized in `main()` because:
- `notes_agent` is used by `ContextRetrievalAgent` for `get_relevant_notes()` (read path — still needed)
- `knowledge_agent` is used by `ContextRetrievalAgent` for `get_relevant_entities()` (read path — still needed)

Only the **write path** (`.process_messages()`) is removed. The read path (context retrieval) is untouched.

**`src/qq/agents/default/default.system.md`** — Add instruction for explicit memory use:

```markdown
## Memory

You have direct control over your memory through tools:
- `memory_add`: Explicitly store information worth remembering
- `memory_query`: Search your memory for specific information
- `memory_verify`: Check if something is already known or conflicts
- `memory_reinforce`: Strengthen existing knowledge with new evidence

Only store information when:
- The user explicitly asks you to remember something
- You encounter a critical fact that will be needed in future conversations
- You learn something that corrects or updates existing knowledge

Do NOT store: routine conversation, temporary context, or information
that is only relevant to the current question.
```

---

## 2. Source Citations (Footnote-style)

**Problem**: Agents answer questions using retrieved context (notes, knowledge graph, file reads) but never tell the user where the information came from. Users can't verify claims.

**Design**: Every answer that draws on memory, knowledge graph, or file reads must include footnote-style citations `[1]` inline, with a `Sources:` block at the bottom listing each source.

### Source Registry

A `SourceRegistry` tracks all sources available during a turn. It collects sources from:
1. **Context retrieval** — notes and entities injected pre-turn (from `ContextRetrievalAgent.prepare_context()`)
2. **File reads** — files read via `read_file` tool during the turn (from `FileManager.pending_file_reads`)
3. **Memory tool calls** — results from `memory_query`, `memory_verify` during the turn

Each source gets a sequential index `[1]`, `[2]`, etc.

### New Module: `src/qq/services/source_registry.py`

```python
class SourceRegistry:
    """Collects and indexes sources during a conversation turn."""

    def __init__(self):
        self._sources = []  # List of {index, type, label, detail}

    def add(self, source_type: str, label: str, detail: str = "") -> int:
        """Register a source, return its [N] index."""
        index = len(self._sources) + 1
        self._sources.append({
            "index": index,
            "type": source_type,   # "note", "entity", "file", "core", "archive"
            "label": label,        # Short identifier (filename, note excerpt, entity name)
            "detail": detail,      # Optional longer info (file path, note_id, similarity score)
        })
        return index

    def format_footer(self) -> str:
        """Format all sources as a markdown footer block."""
        if not self._sources:
            return ""
        lines = ["\n---", "**Sources:**"]
        for s in self._sources:
            detail = f" — {s['detail']}" if s['detail'] else ""
            lines.append(f"[{s['index']}] {s['label']}{detail}")
        return "\n".join(lines)

    def clear(self):
        self._sources.clear()

    @property
    def has_sources(self) -> bool:
        return len(self._sources) > 0
```

### Integration Points

**`src/qq/context/retrieval_agent.py`** — `prepare_context()` registers each retrieved note and entity into the registry, and includes the `[N]` index in the context text so the LLM can reference it:

```
**Relevant Memory Notes:**
- [1] The database runs on port 5432
- [2] API uses JWT authentication

**Related Knowledge:**
- [3] PostgreSQL (Database): Primary data store
```

The LLM sees these indices and can use them in its response. The `SourceRegistry` instance is passed through `prepare_context()` return value.

**`src/qq/services/memory_tools.py`** — `memory_query` and `memory_verify` also register their results into the shared `SourceRegistry` (passed at creation time).

**`src/qq/services/file_manager.py`** — Each `read_file` call registers into the registry: `[N] config.py:1-100`.

**`src/qq/app.py`** — After the agent responds:
1. Get the source footer from `registry.format_footer()`
2. Append it to the displayed response
3. Clear the registry for next turn

**`src/qq/agents/default/default.system.md`** — Add citation instruction:

```markdown
## Source Citations

When your answer draws on retrieved context, memory, or file content,
cite sources using footnote markers [1], [2], etc. that correspond to
the indexed sources shown in your context. The system will append a
Sources block to your response automatically.

Always cite when:
- Stating a fact from memory notes or knowledge graph
- Referencing file content you read
- Drawing on specific entities or relationships

Do not cite for: general knowledge, your own reasoning, or user-provided information.
```

### Source Registry Lifecycle

```
User sends message
  → SourceRegistry created (empty)
  → ContextRetrievalAgent.prepare_context() populates registry with [1]..[N] for notes/entities
  → Context text with [N] markers prepended to user message
  → Agent executes (may call memory_query, read_file — each registers more sources)
  → Agent response may contain [N] references
  → app.py appends registry.format_footer() to displayed response
  → Registry cleared
```

---

## 3. Silent Post-Answer Alignment Agent

**Problem**: The agent answers based on retrieved context but may hallucinate, misattribute sources, or make claims not supported by the cited sources. No verification step exists.

**Design**: A lightweight alignment agent reviews every sourced answer silently. It only surfaces if it finds issues. If everything checks out, the user sees nothing extra.

### New Module: `src/qq/agents/alignment/`

**`alignment.system.md`**:
```markdown
You are a silent answer reviewer. Given an answer and its source materials,
verify that:
1. Every cited source [N] exists and the claim matches the source content
2. No significant claims lack citations when sources were available
3. No source is misquoted or misattributed

Output JSON only:
{
  "pass": true/false,
  "issues": [
    {"type": "missing_citation", "claim": "...", "suggested_source": N},
    {"type": "wrong_citation", "ref": N, "claim": "...", "actual": "..."},
    {"type": "unsupported", "claim": "..."}
  ],
  "corrections": "..." // optional corrected text, only if pass=false
}

If everything checks out, return {"pass": true, "issues": []}.
Be strict but not pedantic — only flag real accuracy issues.
```

**`src/qq/services/alignment.py`**:
```python
class AlignmentAgent:
    """Silent post-answer reviewer."""

    def __init__(self, model):
        self.model = model

    def review(self, answer: str, sources: List[dict], context_text: str) -> dict:
        """Review an answer against its sources.

        Args:
            answer: The agent's response text
            sources: List of source dicts from SourceRegistry
            context_text: The context that was injected pre-turn

        Returns:
            {"pass": bool, "issues": [...], "corrections": str|None}
        """
        # Skip review if no sources were used
        if not sources:
            return {"pass": True, "issues": []}

        # Build review prompt with answer + source materials
        # Call alignment sub-agent
        # Parse JSON response
        # Return result
```

### Integration in `app.py`

After the agent responds but before displaying:

```python
# Only review if sources were used
if source_registry.has_sources:
    review = alignment_agent.review(
        answer=str(response),
        sources=source_registry.sources,
        context_text=context_text,
    )
    if not review["pass"]:
        # Append correction notice
        corrections = review.get("corrections", "")
        if corrections:
            # Replace the response with corrected version
            response = corrections
        else:
            # Append issue warnings
            for issue in review["issues"]:
                console.print_warning(f"[Alignment] {issue['type']}: {issue['claim'][:80]}")
```

The user sees nothing when `pass=True`. When `pass=False`, either a corrected answer replaces the original, or specific warnings appear.

### Performance Consideration

The alignment agent adds one LLM call per sourced response. To mitigate latency:
- Only runs when `source_registry.has_sources` is True (skips unsourced answers)
- Uses the same model instance (no extra initialization)
- Prompt is compact (answer + source excerpts only, not full context)
- Can be disabled via `QQ_ALIGNMENT_ENABLED=false` env var

---

## File Change Summary

| File | Change |
|------|--------|
| `src/qq/app.py` | Remove post-turn `process_messages()` calls; add SourceRegistry lifecycle; add alignment review step |
| `src/qq/agents/default/default.system.md` | Add Memory and Source Citations instructions |
| `src/qq/services/source_registry.py` | **New** — SourceRegistry class |
| `src/qq/services/alignment.py` | **New** — AlignmentAgent class |
| `src/qq/agents/alignment/alignment.system.md` | **New** — Alignment agent system prompt |
| `src/qq/context/retrieval_agent.py` | `prepare_context()` accepts SourceRegistry, indexes sources with [N] |
| `src/qq/services/memory_tools.py` | `create_memory_tools()` accepts SourceRegistry, registers query results |
| `src/qq/services/file_manager.py` | `read_file()` registers into SourceRegistry when available |

## Implementation Order

1. **Source Registry** — Create `source_registry.py` (no dependencies)
2. **Remove passive extraction** — Delete `process_messages()` calls in `app.py`
3. **Wire registry into retrieval** — Update `retrieval_agent.py` to index sources
4. **Wire registry into tools** — Update `memory_tools.py` and `file_manager.py`
5. **Update system prompt** — Add Memory and Citations instructions
6. **App lifecycle** — Wire registry creation/footer/clear in `app.py`
7. **Alignment agent** — Create module and integrate into `app.py`
8. **Test** — End-to-end: ask question, verify citations appear, verify alignment runs silently

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `QQ_ALIGNMENT_ENABLED` | `true` | Enable/disable post-answer alignment review |
| `QQ_CITE_THRESHOLD` | `0.3` | Minimum relevance score for a source to be indexed |
