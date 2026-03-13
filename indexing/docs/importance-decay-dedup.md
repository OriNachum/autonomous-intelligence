# Importance Scoring, Decay & Deduplication

QQ manages note lifecycle through importance scoring, time-based decay, and embedding-based deduplication.

## Importance Scoring

Defined in `src/qq/memory/importance.py`.

### Importance Levels (`importance.py:25-31`)

| Level | Score | Examples |
|-------|-------|----------|
| `core` | 1.0 | User identity, preferences, active projects |
| `high` | 0.7 | Specific decisions, important facts |
| `medium` | 0.4 | Research topics, ongoing investigations |
| `low` | 0.2 | Temporary observations, single-mention facts |

### Initial Scoring (`importance.py:122-174`)

Base score from `importance_hint` (if provided), then adjusted:

**Pattern bonuses:**
- Identity patterns ("my name", "i am", "my role"): +0.3 to +0.5
- Project patterns ("my project", "building", "system"): +0.3
- Specificity patterns (dates, versions, URLs, sizes): +0.05 to +0.1

**Section weights** (`importance.py:55-63`):

| Section | Weight |
|---------|--------|
| Identity | +0.3 |
| People & Entities | +0.2 |
| Projects | +0.2 |
| Important Facts | +0.1 |
| Key Topics | 0.0 |
| Ongoing Threads | 0.0 |
| File Knowledge | -0.1 |

**Length penalties:**
- < 20 characters: -0.1
- > 500 characters: -0.05

Final score clamped to `[0.0, 1.0]`.

## Decay Algorithm (`importance.py:198-243`)

```
decayed = (importance - staleness) * age_factor + access_bonus
```

Where:
- **staleness** = `days_since_last_access * decay_rate`
- **age_factor** = `1.0 / (1 + days_since_creation * 0.01)` (gentle exponential decay)
- **access_bonus** = `min(0.5, access_count * 0.05)` (more accesses = slower decay)

Result clamped to `[0.0, 1.0]`.

### Thresholds

| Threshold | Default | Env Var | Purpose |
|-----------|---------|---------|---------|
| `CORE_THRESHOLD` | 0.8 | `QQ_CORE_THRESHOLD` | Promote to `core.md` |
| `ARCHIVE_THRESHOLD` | 0.05 | `QQ_ARCHIVE_THRESHOLD` | Archive low-importance notes |
| `MIN_RETRIEVAL_IMPORTANCE` | 0.2 | `QQ_MIN_RETRIEVAL_IMPORTANCE` | Minimum to include in context |
| `BASE_DECAY_RATE` | 0.01 | `QQ_BASE_DECAY_RATE` | Default per-note decay rate |

### Retrieval Eligibility (`importance.py:317-336`)

`should_retrieve()` returns `True` if decayed importance >= `MIN_RETRIEVAL_IMPORTANCE`. Used by the retrieval agent to filter context.

### Archival Candidates (`importance.py:265-290`)

`get_archival_candidates()` returns notes where decayed importance < `ARCHIVE_THRESHOLD`.

---

## Deduplication

Defined in `src/qq/memory/deduplication.py`.

### Similarity Detection (`deduplication.py:120-195`)

- O(n^2) pairwise comparison of all notes with embeddings
- Cosine similarity threshold: **0.85** (`DEDUP_THRESHOLD`)
- Returns `DuplicatePair` objects with both notes and similarity score

### Consolidation Strategies

**Simple Consolidation** (`deduplication.py:251-293`):
- Keep the higher-importance note as primary
- Merge: access_count (sum), decay_rate (min), last_accessed (max), created_at (min)
- Boost importance by +0.05 (capped at 1.0)
- Merge source metadata into `source_history`

**LLM-Assisted Consolidation** (`deduplication.py:295-349`):
- Uses Strands Agent to intelligently merge content
- Prompt: preserve unique info, remove redundancy, keep specifics
- Falls back to simple consolidation on LLM failure

### Consolidation Pass (`deduplication.py:351-450`)

`run_consolidation_pass()`:
1. Find all duplicate pairs above threshold
2. For each pair: consolidate content, update primary, archive secondary
3. Push secondary's source into primary's `source_history`
4. Returns `ConsolidationReport` with stats

### Trigger

`should_consolidate()` (`deduplication.py:452-465`):
- Fires when note count exceeds `MAX_WORKING_NOTES` (100)
- Configurable via `QQ_MAX_WORKING_NOTES`

---

## Archival

Defined in `src/qq/memory/archive.py`.

### Archive Format (`archive.py:84-213`)

JSONL file (`archive.jsonl`), one JSON object per line:

```json
{
  "note_id": "...",
  "content": "...",
  "section": "...",
  "importance": 0.03,
  "reason": "importance_decay_0.03",
  "archived_at": "ISO timestamp",
  "original_created_at": "ISO timestamp",
  "access_count": 2,
  "metadata": {},
  "source": {},
  "source_history": []
}
```

### Archival Triggers

- Importance decay below `ARCHIVE_THRESHOLD` (0.05)
- Deduplication (secondary note merged into primary)
- Manual archival

### Restoration (`archive.py:215-285`)

`restore_note()`:
1. Generate new embedding (model may have changed)
2. Boost importance by +0.1
3. Mark as restored in archive (keep history)
4. Add metadata: `restored_from_archive: True`, `restored_at: timestamp`

### Purge (`archive.py:434-481`)

`purge_old_archives()`: Remove notes archived longer than `ARCHIVE_RETENTION_DAYS` (default 90).
