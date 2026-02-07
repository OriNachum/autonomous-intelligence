# File Analyzer: Deep File Internalization

The `analyze_file` tool deeply reads, dissects, and internalizes a file's contents into long-term memory. Unlike `read_file` (which returns raw content for in-context processing), `analyze_file` extracts structured knowledge and persists it across conversations.

## Overview

When the agent calls `analyze_file`, a dedicated analyzer:

1. **Reads the entire file** (bypassing the 100-line sliding window)
2. **Extracts structured knowledge** via a specialized LLM agent
3. **Stores notes** in MongoDB (with embeddings) and notes.md
4. **Stores entities and relationships** in the Neo4j knowledge graph
5. **Returns a concise summary** to the calling agent

After analysis, the file's knowledge is available through context retrieval and memory tools — no need to re-read the file.

```
┌──────────────────────┐
│   Agent calls        │
│   analyze_file()     │
└──────────┬───────────┘
           │
           ▼
┌──────────────────────┐
│    FileAnalyzer      │
│  (services/analyzer) │
└──────────┬───────────┘
           │
    ┌──────┴──────┐
    ▼             ▼
┌────────┐   ┌────────────────────┐
│ Read   │   │ Analyzer Agent     │
│ full   │──▶│ (LLM extraction)   │
│ file   │   │ Structured JSON    │
└────────┘   └────────┬───────────┘
                      │
           ┌──────────┼──────────┐
           ▼          ▼          ▼
      ┌─────────┐ ┌────────┐ ┌────────┐
      │ MongoDB │ │notes.md│ │ Neo4j  │
      │ (notes) │ │        │ │(graph) │
      └─────────┘ └────────┘ └────────┘
```

## Usage

### Basic Analysis

```
analyze_file("src/qq/app.py")
```

Performs general-purpose analysis — extracts overview, key concepts, entities, relationships, and important facts.

### Focused Analysis

```
analyze_file("src/qq/app.py", focus="error handling patterns")
```

Guides the extraction toward a specific area while still capturing the most important general knowledge.

### Batch Analysis (Pattern Matching)

```
analyze_file(pattern=r"\.py$", path="src/qq/services/", focus="error handling")
```

Analyzes all files under the given path whose relative paths match the regex pattern. Each matched file is analyzed individually, and results are aggregated into a single response.

**Parameters when using pattern:**
- `pattern`: Regex pattern matched against relative file paths (e.g., `r"\.py$"` for Python files, `r"test_"` for test files)
- `path`: Base directory to search in (defaults to session working directory)
- `focus`: Optional focus area applied to every matched file

**Common patterns:**

| Pattern | Matches |
|---------|---------|
| `r"\.py$"` | All Python files |
| `r"test_"` | Files starting with `test_` |
| `r"services/.*\.py$"` | Python files in services/ subdirectory |
| `r"\.(md\|txt)$"` | Markdown and text files |

**Safety cap:** A maximum of 50 files can be analyzed per pattern match. If more files match, narrow the pattern or base path.

### What Gets Returned

A concise summary:

```
Analyzed app.py (473 lines)
Extracted: 8 notes (6 new, 2 reinforced), 12 entities, 9 relationships
Overview: Main orchestration module — initializes agents, memory, context
retrieval, alignment review. Runs CLI and console modes with token recovery.
Key findings:
  - Session isolation via FileManager instance state
  - Context injection happens before each turn via ContextRetrievalAgent
  - Token limit recovery with progressive context reduction (up to 4 retries)
```

## What Gets Stored

### Notes (MongoDB + notes.md)

Each extracted fact becomes a note with:
- **Content**: Self-contained, specific description
- **Section**: Key Topics, Important Facts, File Knowledge, etc.
- **Embedding**: Vector for semantic search
- **Importance**: 0.6 (slightly above normal — file-extracted knowledge)
- **Source provenance**: File path, checksum, git metadata, analysis timestamp

### Entities (Neo4j)

Named things found in the file: classes, functions, services, configs. Each entity includes:
- **Name**: As it appears in the code
- **Type**: Concept, Person, Topic, etc.
- **Description**: What it does
- **Embedding**: Vector for similarity search
- **Source link**: `EXTRACTED_FROM` edge to a Source node

### Relationships (Neo4j)

How entities connect: CALLS, EXTENDS, DEPENDS_ON, CONFIGURES, CONTAINS. Each relationship includes:
- **Source and target** entities
- **Type**: Uppercase with underscores
- **Description**: How they relate
- **Confidence**: 0.0-1.0
- **Source link**: `EVIDENCES` edge to a Source node

## Re-analysis Detection

The analyzer tracks file checksums. If you analyze a file that hasn't changed since the last analysis, it returns early:

```
File already analyzed with same content: app.py
Checksum: sha256:abc123...
Use memory_query to search for previously extracted knowledge.
```

If the file has changed (different checksum), a fresh analysis is performed.

## Large File Handling

Files exceeding ~30,000 characters are automatically split into chunks at line boundaries. Each chunk is analyzed independently, and results are merged:
- Overviews are concatenated
- Entities are deduplicated by name
- Relationships are deduplicated by (source, target, type)
- Notes are collected from all chunks

## Deduplication

Before storing each note, the analyzer checks MongoDB for near-duplicates (cosine similarity >= 0.85). If a match is found, the existing note is reinforced (importance boosted, source appended to history) instead of creating a duplicate.

## When to Use

| Scenario | Tool |
|----------|------|
| Quick glance at a file | `read_file` |
| Understanding + remembering a file | `analyze_file` |
| Checking a specific line range | `read_file` with start_line |
| Internalizing a codebase component | `analyze_file` |
| Re-reading after file changed | `analyze_file` (detects changes via checksum) |
| Analyzing all files matching a pattern | `analyze_file` with `pattern` |
| Batch analysis of a directory | `analyze_file(pattern=r"\.py$", path="src/")` |

## Implementation

| File | Purpose |
|------|---------|
| `src/qq/services/analyzer.py` | `FileAnalyzer` class and `create_analyzer_tool()` |
| `src/qq/agents/analyzer_agent/analyzer_agent.system.md` | LLM extraction prompt |
| `src/qq/agents/__init__.py` | Tool registration (alongside memory tools) |
| `src/qq/memory/mongo_store.py` | `find_by_source_file()` for re-analysis detection |
