# File Analysis Reference

Deep file analysis that reads, dissects, and internalizes file contents into all memory layers (notes.md, MongoDB, Neo4j).

## Module

```python
from qq.services.analyzer import FileAnalyzer, create_analyzer_tool
```

## Constructor

```python
analyzer = FileAnalyzer(file_manager, model=None)
# file_manager: FileManager instance for path resolution and document reading
# model: Optional. If None, uses get_model() on first call (lazy init)
```

## API

### Analyze Single File

```python
analyzer.analyze(path: str, focus: str = "") -> str
```

- `path`: Absolute or relative to session directory
- `focus`: Optional focus area (e.g., "API endpoints", "error handling", "data model")
- Returns: summary string describing what was analyzed and stored

### Analyze by Pattern

```python
analyzer.analyze_pattern(pattern: str, base_path: str = "", focus: str = "") -> str
```

- `pattern`: Regex pattern to match against relative file paths (e.g., `r"\.py$"`, `r"test_.*\.py$"`)
- `base_path`: Directory to search in (defaults to file_manager cwd)
- `focus`: Optional focus area
- Returns: aggregated summaries of all matched files
- Limit: max 1000 files per pattern match

### Strands Tool

```python
tool_fn = create_analyzer_tool(file_manager)
# Creates the analyze_files @tool function for Strands Agent integration
# Tool params: path, focus, pattern
```

## Workflow

1. **Read file** — text files directly, binary (PDF/DOCX/XLSX/PPTX) via DocumentReader
2. **Collect metadata** — file path, checksum (`sha256`), git metadata (branch, commit, author)
3. **Re-analysis detection** — check MongoDB for existing notes with same checksum; skip if found
4. **LLM extraction** — send to analyzer agent, chunked if >30,000 chars (~7500 tokens)
   - Returns JSON: `{overview, notes[], entities[], relationships[]}`
5. **Store knowledge**:
   - Notes → MongoDB (with embeddings) + `notes.md`
   - Entities/Relationships → Neo4j knowledge graph
   - Dedup check: if similarity >= 0.85, reinforce existing note instead of creating new
6. **Return summary** — overview + extraction stats + key findings

## Supported Formats

| Format | Method |
|--------|--------|
| `.py`, `.md`, `.txt`, `.json`, etc. | Direct text read |
| `.pdf` | DocumentReader (pdfplumber) |
| `.docx` | DocumentReader (python-docx) |
| `.xlsx` | DocumentReader (openpyxl) |
| `.pptx` | DocumentReader (python-pptx) |

## Source Provenance

Each analyzed file creates a source record:

```python
{
    "source_type": "file",
    "file_path": "/absolute/path/to/file.py",
    "file_name": "file.py",
    "checksum": "sha256_hex",
    "git_metadata": {
        "branch": "main",
        "commit": "abc123",
        "author": "user",
        "date": "2025-01-15"
    },
    "analyzed_at": "2025-01-15T10:30:00",
    "analyzer_focus": "error handling"  # if focus provided
}
```

## Backend Degradation

The analyzer initializes backends lazily and handles missing services:

| Backend Missing | Behavior |
|----------------|----------|
| Embeddings | Notes stored without vectors (no similarity search) |
| MongoDB | Notes stored in `notes.md` only |
| Neo4j (graph) | Entities and relationships not stored |
| All available | Full extraction into all layers |

## Configuration

| Constant | Value | Description |
|----------|-------|-------------|
| `MAX_CHARS_PER_CHUNK` | 30,000 | Chunk boundary for large files |
| `ANALYZER_IMPORTANCE` | 0.8 | Default importance for extracted notes |
| `MAX_PATTERN_FILES` | 1,000 | Max files in batch analysis |
| `DEDUP_THRESHOLD` | 0.85 | Cosine similarity for dedup |

## Example

```python
# Single file analysis
result = analyzer.analyze("src/qq/memory/mongo_store.py", focus="API surface")
print(result)
# Analyzed mongo_store.py (450 lines)
# Extracted: 8 notes (6 new, 2 reinforced), 3 entities, 5 relationships
# Overview: MongoDB notes store with vector search and importance scoring...
# Key findings:
#   - Uses cosine similarity for vector search
#   - Supports source provenance tracking
#   - Implements importance decay with access counting

# Batch analysis
result = analyzer.analyze_pattern(r"\.py$", "src/qq/memory/", focus="data model")
```
