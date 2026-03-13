# Source & Provenance Indexing

Every piece of knowledge in QQ tracks its origin with SHA-256 checksums, git metadata, and citation pipelines.

## SourceRecord

Defined in `src/qq/memory/source.py:23-89`.

Each note, entity, and relationship carries a `SourceRecord` with:

| Field | Description |
|-------|-------------|
| `source_type` | `file`, `conversation`, `user_input`, or `derived` |
| `file_path` | Absolute path to source file |
| `checksum` | `sha256:{hex_digest}` of file contents |
| `git_repo` | Git repository root |
| `git_branch` | Branch name |
| `git_commit` | Commit hash |
| `git_author` | Last commit author |
| `session_id` | QQ session that created this record |
| `agent_id` | Agent that performed extraction |
| `confidence` | Extraction confidence score |
| `extraction_model` | LLM model used |

The `source_id` property returns either the file checksum or session ID as a unique identifier.

## File Checksum Tracking

`compute_file_checksum()` (`source.py:91-101`) generates SHA-256 hashes:

```python
sha256:{hex_digest}
```

Stored in MongoDB as `source.checksum` and indexed. Used by the analyzer to detect whether a file has already been analyzed (skip re-analysis if checksum matches).

## Git Metadata Collection

`collect_git_metadata()` (`source.py:104-157`) extracts:
- Repository root path
- Current branch
- Latest commit hash
- Last commit author

Results are cached per repository to avoid repeated subprocess calls. Fails gracefully for files not in a git repo.

## Citation Pipeline (`[N]` Indexing)

The `SourceRegistry` (`src/qq/services/source_registry.py:11-75`) assigns sequential `[N]` indices during response generation:

1. `add(source_type, label, detail)` -- returns a 1-based index for each source
2. Source types: `"note"`, `"entity"`, `"file"`, `"core"`, `"archive"`
3. `format_footer()` -- generates a markdown footer listing all cited sources

The retrieval agent injects these indices into the context so the LLM can cite `[1]`, `[2]`, etc. in its answers.

## Neo4j Source Nodes

`neo4j_client.py:183-293` creates Source nodes in the knowledge graph:

```cypher
(:Source {
  source_id, source_type, file_path, file_name,
  checksum, git_repo, git_branch, git_commit,
  session_id, verified, created_at, last_verified,
  mongo_note_ids  -- linked MongoDB notes
})
```

Linking edges:
- `EXTRACTED_FROM`: Entity --> Source (which source created this entity)
- `EVIDENCES`: Source --> Entity (what relationship this source provides evidence for)

`update_source_verification()` (`neo4j_client.py:276-292`) re-checks file checksums to flag stale sources.

## Source History (Audit Trail)

MongoDB's `append_source_history()` (`mongo_store.py:370-405`) preserves the full provenance chain:
- Each time a note is reinforced from a new source, the new SourceRecord is appended to `source_history[]`
- The current `source` field always reflects the latest source
- No truncation -- complete audit trail preserved
