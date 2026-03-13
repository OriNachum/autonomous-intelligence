# File Analysis Pipeline

The analyzer agent performs deep file internalization -- reading files, extracting structured knowledge, and storing it across all memory layers.

## Entry Point

`analyze()` in `src/qq/services/analyzer.py:456-532`:

1. Read full file content
2. Compute SHA-256 checksum + collect git metadata
3. Check for re-analysis (if checksum matches existing MongoDB source, skip)
4. Extract knowledge via LLM (chunked if large)
5. Store notes + entities + relationships
6. Return summary with stats

## Chunking Strategy (`analyzer.py:241-262`)

For files larger than 30,000 characters (~7,500 tokens):

- Split on line boundaries (no mid-line breaks)
- `MAX_CHARS_PER_CHUNK`: 30,000
- Each chunk processed independently with context: `"[Chunk N/M of filename]"`
- `merge_results()` (`analyzer.py:264-300`): Deduplicate entities and notes across chunks

## LLM Extraction (`analyzer.py:215-239`)

Uses the `analyzer_agent` system prompt. Returns structured JSON per chunk:

```json
{
  "overview": "high-level summary",
  "notes": [
    {"content": "...", "section": "Key Topics", "importance": "high"}
  ],
  "entities": [
    {"name": "...", "type": "Person", "description": "...", "aliases": [], "confidence": 0.9}
  ],
  "relationships": [
    {"source": "...", "target": "...", "type": "WORKS_ON", "description": "...", "evidence": "..."}
  ]
}
```

## Knowledge Storage (`analyzer.py:306-398`)

### Notes
- Stored in both MongoDB and `notes.md`
- Default importance: `ANALYZER_IMPORTANCE` (0.8) -- file knowledge starts high
- Each note gets an embedding
- Deduplication check: cosine similarity against existing notes (threshold 0.85)
- If duplicate found: `append_source_history()` + boost importance instead of creating new note

### Entities & Relationships
- Stored in Neo4j via the knowledge graph pipeline
- File source linked via `EXTRACTED_FROM` edges
- Embeddings generated for all entities

## Re-Analysis Detection (`analyzer.py:190-209`)

Before analyzing a file:
1. Compute current SHA-256 checksum
2. Query MongoDB for existing notes with matching `source.checksum`
3. If match found: skip analysis (file unchanged)
4. If no match: proceed with full analysis

This prevents redundant processing when files haven't changed.

## Batch Analysis (`analyzer.py:404-450`)

`analyze_pattern(regex_pattern, base_path, focus)`:
- Find all files matching a regex pattern
- Analyze each file independently
- Aggregate results across all files
- Limit: `MAX_PATTERN_FILES` (1,000)
