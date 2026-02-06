# Anchoring Answers in Sources

How qq traces every claim back to its origin — from context retrieval through citation to post-answer alignment review.

## Overview

Every answer qq produces follows a three-stage pipeline:

1. **Source Indexing** — Retrieved context items (notes, entities, files) are assigned sequential `[N]` indices via a `SourceRegistry`.
2. **Cited Response** — The LLM sees indexed items in its context and references them with `[N]` markers in its answer.
3. **Alignment Review** — A silent post-answer agent checks that citations match their sources and flags issues.

The result is a response with a `Sources:` footer mapping each `[N]` back to its origin, reviewed for accuracy before the user sees it.

## Architecture

```
User query
    │
    ▼
┌──────────────────────────┐
│  SourceRegistry created  │  (app.py, per-turn)
└──────────┬───────────────┘
           │
           ▼
┌──────────────────────────┐
│  Context Retrieval       │  retrieval_agent.py
│  ├─ Core notes   → [1]  │
│  ├─ Working notes→ [2]  │
│  ├─ Entities     → [3]  │
│  └─ (+ memory_query)    │
└──────────┬───────────────┘
           │  context_text with [N] markers
           ▼
┌──────────────────────────┐
│  LLM generates answer    │  Uses [N] in response
│  + memory_query/read_file│  → more sources added
└──────────┬───────────────┘
           │  response_text
           ▼
┌──────────────────────────┐
│  Alignment Review        │  alignment.py (silent)
│  Checks citations vs     │
│  source content          │
└──────────┬───────────────┘
           │  possibly corrected
           ▼
┌──────────────────────────┐
│  Source Footer appended  │  source_registry.format_footer()
└──────────┬───────────────┘
           │
           ▼
        User sees response + Sources block
```

## Components

### SourceRegistry (`services/source_registry.py`)

A per-turn collector that assigns sequential `[N]` indices to every piece of retrieved information.

```python
registry = SourceRegistry()

# Context retrieval registers items
idx = registry.add("note", "User prefers dark themes", "note:abc123 score=0.82")
# idx == 1

# File reads register automatically
idx = registry.add("file", "config.py:10-25", "/home/user/project/config.py")
# idx == 2

# After LLM responds, format the footer
footer = registry.format_footer()
# "\n---\n**Sources:**\n[1] User prefers dark themes — note:abc123 score=0.82\n[2] config.py:10-25 — /home/user/project/config.py"
```

**Source types:**

| Type | Origin | Detail format |
|------|--------|---------------|
| `core` | Core memory (user profile) | `core/{category}` |
| `note` | Working notes (MongoDB) | `note:{id} [{section}] score={n}` |
| `entity` | Knowledge graph (Neo4j) | `score={n}` |
| `file` | File reads via FileManager | Full file path |
| `archive` | Archived notes | `archive:{id}` |

**Lifecycle:** Created at the start of each turn in `app.py`, set on `file_manager.source_registry`, passed to `context_agent.prepare_context()`, and cleared after the response is output.

### Context Retrieval (`context/retrieval_agent.py`)

When a `SourceRegistry` is provided to `prepare_context()`, each retrieved item is registered and prefixed with its `[N]` index:

```
**Core Memory (User Profile):**
- [1] Prefers concise answers
- [2] Works on Python projects

**Relevant Memory Notes:**
- [3] Discussed Neo4j schema migration last week

**Related Knowledge:**
- [4] **Neo4j** (technology): Graph database used for knowledge storage
```

Items below the cite threshold (`QQ_CITE_THRESHOLD`, default `0.3`) are excluded from indexing.

### Mid-turn Source Registration

Sources can also be registered during the LLM's tool calls:

- **`memory_query`** — Results from memory searches are registered via `file_manager.source_registry.add(...)` in `memory_tools.py`.
- **`read_file`** — File reads are registered via `file_manager.source_registry.add(...)` in `file_manager.py`.

This means the source list grows as the LLM uses tools, and the final footer reflects everything that contributed to the answer.

### Alignment Agent (`services/alignment.py`)

A silent post-answer reviewer that runs one LLM call after each sourced response. It only surfaces when citation issues are found.

**When it runs:** Only when `source_registry.has_sources` is `True` — i.e., the response drew on retrieved context.

**What it checks:**
1. Every cited `[N]` exists and the claim it supports matches the source content
2. No significant claims lack citations when sources were available
3. No source is misquoted or misattributed

**Output protocol (JSON):**

```json
{
  "pass": true,
  "issues": []
}
```

Or when issues are found:

```json
{
  "pass": false,
  "issues": [
    {"type": "missing_citation", "claim": "Neo4j uses...", "suggested_source": 4},
    {"type": "wrong_citation", "ref": 2, "claim": "...", "actual": "..."},
    {"type": "unsupported", "claim": "..."}
  ],
  "corrections": "Full corrected answer text (optional)"
}
```

**Behavior:**
- If `corrections` is provided and `pass` is false, the corrected text replaces the original response.
- If only `issues` are listed without a full correction, individual warnings are printed to the console.
- Alignment failures are non-fatal — any exception defaults to `{"pass": true}`.

**Configuration:**
- `QQ_ALIGNMENT_ENABLED` — Set to `false`, `0`, or `no` to disable (default: enabled).

### System Prompt Integration (`agents/default/default.system.md`)

The agent's system prompt instructs the LLM to use footnote-style citations:

> When my answer draws on retrieved context, memory, or file content,
> I cite sources using footnote markers [1], [2], etc. that correspond to
> the indexed sources shown in my context.

**Citation rules:**
- Cite when stating facts from memory notes or knowledge graph
- Cite when referencing file content
- Do not cite for general knowledge, own reasoning, or user-provided information

## Turn Lifecycle

The full flow in `app.py` for each conversation turn:

```python
# 1. Create per-turn registry
source_registry = SourceRegistry()
file_manager.source_registry = source_registry

# 2. Retrieve context with source indexing
context_data = context_agent.prepare_context(
    user_input, source_registry=source_registry
)
context_text = context_data.get("context_text", "")
formatted_input = f"{context_text}\n\n{user_input}"

# 3. LLM generates response (may call tools that add more sources)
result = execute_with_recovery(agent_fn=lambda msg: agent(msg), ...)
response_text = str(result.response)

# 4. Alignment review (silent unless issues found)
response_text = _run_alignment_review(
    alignment_agent, response_text, source_registry, context_text, console
)

# 5. Append source footer
source_footer = source_registry.format_footer()
if source_footer:
    response_text += source_footer

# 6. Output and clean up
console.print_assistant_message(response_text)
source_registry.clear()
file_manager.source_registry = None
```

## Example Output

```
Based on your previous notes [1], you configured Neo4j [3] with a custom
schema for entity extraction. The config file [2] shows the connection
settings on line 15.

---
**Sources:**
[1] Discussed Neo4j schema migration last week — note:abc123 [general] score=0.82
[2] config.py:10-25 — /home/user/project/config.py
[3] **Neo4j** (technology) — score=0.91
```

## Design Decisions

**Why per-turn registries?** Tools are created once at agent load time, but source tracking must be per-turn. The registry is stored as a mutable attribute on `file_manager` and accessed dynamically — no static binding needed.

**Why silent alignment?** The alignment agent only speaks up when something is wrong. Users see clean answers with a source footer; corrections happen transparently unless the issue is minor (in which case a console warning is printed).

**Why footnote-style?** Inline `[N]` markers are compact, familiar from academic writing, and easy for both the LLM to produce and the alignment agent to verify.

**Why a cite threshold?** Low-relevance retrievals (score < 0.3) are noise. Excluding them from the registry keeps the source list meaningful and prevents the LLM from citing irrelevant context.

## Passive Extraction Removal

Previously, notes and knowledge graph entities were automatically extracted from every conversation turn post-response. This was removed in favor of explicit-only memory writes:

- Memory is only stored when the agent calls `memory_add` (user-requested or agent-judged critical)
- `memory_reinforce` updates existing knowledge with new evidence
- No automatic post-turn extraction pipelines run

This keeps the memory clean, intentional, and auditable.
