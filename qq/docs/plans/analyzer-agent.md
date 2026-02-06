# File Analyzer Agent Plan

Add an `analyze_file` tool that deeply reads, dissects, and internalizes a file — extracting structured knowledge into both memory (notes + MongoDB) and the knowledge graph (Neo4j entities + relationships). Unlike `read_file` which returns raw content for the model to process in-context, `analyze_file` delegates to a dedicated analyzer agent that processes the file independently and persists everything it learns.

## Goal

When the model calls `analyze_file("src/qq/app.py")`, a dedicated agent:
1. Reads the entire file (handling large files via chunked reads)
2. Extracts structured knowledge: purpose, key concepts, entities, relationships, important facts
3. Stores extracted knowledge in memory (notes.md + MongoDB with embeddings)
4. Stores entities and relationships in the knowledge graph (Neo4j)
5. Returns a concise summary to the calling agent

The file's content is **internalized** — future conversations can recall what was learned via context retrieval and memory tools, without re-reading the file.

## Current State

- `read_file` returns raw content (100 lines at a time) into the conversation context — ephemeral, not stored
- `memory_add/query/verify/reinforce` let the agent manually store facts — but require the agent to decide what to store
- `KnowledgeGraphAgent.process_messages()` extracts entities/relationships from conversation history — but only runs on conversations, not on files directly
- Entity/relationship agents exist but are coupled to conversation message format

## Design

### New Tool: `analyze_file`

```python
@tool
def analyze_file(path: str, focus: str = "") -> str:
    """
    Deeply analyze a file: read, dissect, and internalize its contents into memory.

    Unlike read_file (which shows raw content), this tool:
    - Reads the entire file regardless of size
    - Extracts key concepts, entities, relationships, and important facts
    - Stores everything in long-term memory and knowledge graph
    - Returns a concise analysis summary

    Use this when you want to truly understand and remember a file's contents,
    not just glance at it.

    Args:
        path: Path to the file to analyze (absolute or relative to session directory).
        focus: Optional focus area to guide analysis (e.g., "API endpoints",
               "error handling patterns", "data model"). If empty, performs
               general-purpose analysis.
    """
```

**Returns**: A structured summary string containing:
- File overview (purpose, language, size)
- Key findings (what was learned)
- What was stored (N notes, N entities, N relationships)
- Focus-specific insights (if focus was provided)

### Architecture

```
analyze_file (tool, registered in agents/__init__.py)
    │
    ├── FileAnalyzer (new class in src/qq/services/analyzer.py)
    │   │
    │   ├── Step 1: Read entire file
    │   │   └── FileManager.read_file() in chunks → concatenate full content
    │   │
    │   ├── Step 2: Extract knowledge via dedicated Strands Agent
    │   │   └── Analyzer Agent (system prompt optimized for file dissection)
    │   │       - Input: full file content + focus hint
    │   │       - Output: structured JSON with extracted knowledge
    │   │
    │   ├── Step 3: Store in memory
    │   │   ├── MongoDB (MongoNotesStore) — each fact with embedding + source provenance
    │   │   └── notes.md (NotesManager) — section-appropriate entries
    │   │
    │   ├── Step 4: Store in knowledge graph
    │   │   └── Neo4j via KnowledgeGraphAgent._store_extraction()
    │   │       - Entities with embeddings
    │   │       - Relationships with evidence
    │   │       - Source nodes linking back to the file
    │   │
    │   └── Step 5: Return summary
    │       └── Concise text: what was analyzed, what was learned, what was stored
```

### Why a Dedicated Agent (Not the Sub-Agent System)

The child process / sub-agent system (`ChildProcess.spawn_agent()`) spawns entirely new QQ processes with their own sessions, ephemeral notes, and CLI overhead. This is overkill for file analysis because:

1. **No CLI needed** — we don't need a full QQ session, just an LLM call with a specialized prompt
2. **Direct memory access** — the analyzer needs to write directly to the shared memory stores (MongoDB, Neo4j, notes.md), not to ephemeral per-child notes
3. **No process overhead** — spawning a subprocess for each file is expensive; a Strands Agent call is lightweight
4. **Shared backends** — reuse the already-initialized embedding client, MongoDB, and Neo4j connections

Instead, `FileAnalyzer` creates a lightweight Strands `Agent` internally (same pattern as `EntityAgent`, `RelationshipAgent`, `NormalizationAgent`) — just an LLM call with a specialized system prompt, no tools, no subprocess.

### Extraction Prompt Design

The analyzer agent receives a system prompt optimized for structured file analysis. The user message contains the file content and optional focus.

**System prompt** (`src/qq/agents/analyzer_agent/analyzer_agent.system.md`):

```
You are a file analysis specialist. Your job is to deeply analyze source files
and extract structured knowledge that should be remembered long-term.

Given a file's contents, extract:

1. **Overview**: Purpose, language/format, key responsibility
2. **Key Concepts**: Important abstractions, patterns, design decisions
3. **Entities**: Named things (classes, functions, services, configs, people, projects)
4. **Relationships**: How entities connect (calls, extends, depends_on, configures)
5. **Important Facts**: Specific values, constraints, gotchas, undocumented behavior
6. **File Knowledge**: What this file does in the broader system context

Respond with valid JSON only:
{
  "overview": "One paragraph describing the file's purpose and role",
  "notes": [
    {"section": "Key Topics|Important Facts|File Knowledge", "content": "..."},
    ...
  ],
  "entities": [
    {"name": "...", "type": "Concept|Person|Topic|...", "description": "..."},
    ...
  ],
  "relationships": [
    {"source": "...", "target": "...", "type": "CALLS|EXTENDS|DEPENDS_ON|...",
     "description": "...", "confidence": 0.9},
    ...
  ]
}
```

### File Reading Strategy

Large files need chunked reading. The analyzer handles this internally:

```python
def _read_full_file(self, path: str) -> Tuple[str, dict]:
    """Read entire file content, handling large files via chunks."""
    resolved = self.file_manager._resolve_path(path)

    # Use DocumentReader for binary formats
    suffix = resolved.suffix.lower()
    if suffix in ['.pdf', '.docx', '.xlsx', '.pptx']:
        content = self.file_manager.document_reader.convert(resolved)
    else:
        content = resolved.read_text()

    # Collect source metadata
    from qq.memory.source import compute_file_checksum, collect_git_metadata
    source_meta = {
        "source_type": "file",
        "file_path": str(resolved),
        "file_name": resolved.name,
        "checksum": compute_file_checksum(str(resolved)),
        "git_metadata": collect_git_metadata(str(resolved)),
    }

    return content, source_meta
```

This bypasses the 100-line sliding window of `read_file` — the analyzer reads the full file directly since it needs complete context for analysis.

### Chunked Analysis for Large Files

Files exceeding model context limits need chunked analysis:

```python
MAX_CHARS_PER_CHUNK = 30000  # ~7500 tokens, safe for most models

def _analyze_large_file(self, content, file_meta, focus):
    """Split large files into chunks and analyze each."""
    chunks = self._split_into_chunks(content, MAX_CHARS_PER_CHUNK)
    all_results = []

    for i, chunk in enumerate(chunks):
        chunk_context = f"[Chunk {i+1}/{len(chunks)} of {file_meta['file_name']}]"
        result = self._run_extraction(chunk, focus, chunk_context)
        all_results.append(result)

    return self._merge_results(all_results)
```

### Storage Flow

After extraction, the analyzer stores everything:

```python
def _store_knowledge(self, extraction, source_meta):
    """Store extracted knowledge in memory and knowledge graph."""

    # 1. Store notes in MongoDB + notes.md
    for note in extraction.get("notes", []):
        embedding = self.embeddings.get_embedding(note["content"])

        # Dedup check
        duplicates = self.mongo.search_similar(embedding, limit=1)
        if duplicates and duplicates[0].get("score", 0) >= 0.85:
            # Reinforce instead
            self.mongo.append_source_history(
                duplicates[0]["note_id"], source_meta, boost_importance=0.1
            )
            continue

        note_id = generate_note_id()
        self.mongo.upsert_note(
            note_id=note_id,
            content=note["content"],
            embedding=embedding,
            section=note["section"],
            importance=0.6,  # file-extracted notes start slightly above normal
            source=source_meta,
        )
        self.notes_manager.add_item(note["section"], note["content"])

    # 2. Store entities + relationships in Neo4j
    #    Reuse KnowledgeGraphAgent._store_extraction() for consistency
    graph_data = {
        "entities": extraction.get("entities", []),
        "relationships": extraction.get("relationships", []),
    }
    file_sources = {source_meta["file_path"]: source_meta}
    self.knowledge_agent._store_extraction(
        graph_data,
        file_sources=file_sources,
    )
```

### Source Provenance

Every piece of extracted knowledge links back to the analyzed file:

```python
source = {
    "source_type": "file",
    "file_path": "/absolute/path/to/file.py",
    "file_name": "file.py",
    "checksum": "sha256:abc123...",
    "git_metadata": {
        "commit": "0fefcd5",
        "branch": "main",
        "author": "...",
    },
    "analyzed_at": "2026-02-07T...",
    "analyzer_focus": "API endpoints",  # if focus was specified
}
```

This enables:
- Re-analysis detection (skip if checksum unchanged)
- Source citations in responses (`[from file: app.py]`)
- Staleness detection (file changed since last analysis)

### Re-analysis Detection

Before analyzing, check if the file was already analyzed with the same checksum:

```python
def _already_analyzed(self, file_path, checksum):
    """Check if file was already analyzed with this exact content."""
    existing = self.mongo.find_by_source_file(file_path)
    if existing:
        for note in existing:
            src = note.get("source", {})
            if src.get("checksum") == checksum:
                return True
    return False
```

If already analyzed, return early with a message. If the file changed (different checksum), re-analyze and update existing notes.

## File Changes

| File | Change |
|------|--------|
| New: `src/qq/services/analyzer.py` | `FileAnalyzer` class — orchestrates reading, extraction, storage |
| New: `src/qq/agents/analyzer_agent/analyzer_agent.system.md` | System prompt for the extraction LLM |
| `src/qq/agents/__init__.py` | Register `analyze_file` tool in `_create_common_tools()` or alongside memory tools |
| `src/qq/memory/mongo_store.py` | Add `find_by_source_file(file_path)` method for re-analysis detection |
| New: `docs/analyzer-agent.md` | User-facing documentation for the analyze_file feature |

## Dependencies

No new dependencies. Reuses:
- `strands.Agent` — for the extraction LLM call
- `MongoNotesStore` — notes storage
- `NotesManager` — notes.md file
- `EmbeddingClient` — vector embeddings
- `KnowledgeGraphAgent._store_extraction()` — entity/relationship storage
- `FileManager` — path resolution and document conversion
- `SourceRecord` utilities — provenance metadata

## Tool Registration

The `analyze_file` tool is created in a new `_create_analyzer_tool()` function (or within the existing `create_memory_tools()`) that captures:
- `FileManager` instance (for path resolution + document reading)
- Lazy-initialized backends (same pattern as memory tools)

```python
# In agents/__init__.py, alongside memory tools:
from qq.services.analyzer import create_analyzer_tool

analyzer_tool = create_analyzer_tool(file_manager=file_manager)
agent_tools.append(analyzer_tool)
```

## Initialization

All backends are lazy-initialized (same as memory tools):
- `EmbeddingClient` — connects on first embedding request
- `MongoNotesStore` — connects on first store/search
- `KnowledgeGraphAgent` — connects Neo4j on first graph operation
- Analyzer Strands Agent — created on first `analyze_file` call

No new startup cost for agents that don't use `analyze_file`.

## Example Flow

```
User: "analyze the app.py file so you remember how it works"

Agent calls: analyze_file(path="src/qq/app.py")

FileAnalyzer:
  1. Reads full file (473 lines)
  2. Computes checksum → not previously analyzed
  3. Sends to analyzer agent with system prompt
  4. Gets JSON extraction:
     - overview: "Main application orchestration for QQ..."
     - 8 notes (Key Topics, Important Facts, File Knowledge)
     - 12 entities (qqConsole, History, ContextRetrievalAgent, ...)
     - 9 relationships (main→load_agent CALLS, ContextRetrievalAgent→NotesAgent DEPENDS_ON, ...)
  5. Stores 8 notes in MongoDB + notes.md (2 reinforced existing)
  6. Stores 12 entities + 9 relationships in Neo4j
  7. Returns summary

Tool returns:
  "Analyzed src/qq/app.py (473 lines, Python)
   Extracted: 8 notes (6 new, 2 reinforced), 12 entities, 9 relationships
   Overview: Main orchestration module — initializes agents, memory, context
   retrieval, alignment review. Runs CLI and console modes with token recovery.
   Key findings: Session isolation via FileManager, context injection before
   each turn, source citation registry per-turn, progressive token recovery."

Agent responds to user with the summary + its own interpretation.

Later conversation:
User: "how does the console mode work?"
→ Context retrieval finds the stored notes about run_console_mode
→ Agent can answer from memory without re-reading the file
```

## Verification

1. **Unit test**: `analyze_file` on a small test file → verify notes in MongoDB, entities in Neo4j
2. **Re-analysis**: Analyze same file twice → second call detects existing checksum, skips or reports "already analyzed"
3. **Large file**: Analyze a 1000+ line file → verify chunked analysis produces merged results
4. **Focus**: `analyze_file("app.py", focus="error handling")` → verify focus-relevant notes are prioritized
5. **Memory recall**: After analysis, `memory_query("how does app.py work")` → returns stored notes
6. **Context injection**: After analysis, ask a question about the file → context retrieval pulls relevant notes automatically

## Documentation

After implementation, create `docs/analyzer-agent.md` with:
- Feature overview and purpose (why `analyze_file` vs `read_file`)
- Usage examples (basic, with focus, re-analysis behavior)
- What gets stored (notes, entities, relationships) and where
- Architecture diagram (tool → FileAnalyzer → extraction agent → storage)
- Configuration (chunk size, importance defaults, re-analysis detection)
- Limitations and known constraints
