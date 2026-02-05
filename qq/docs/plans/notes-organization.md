# Notes Organization & Memory Fragmentation Plan

## Problem Statement

The QQ memory system grows unboundedly. Every conversation triggers note extraction, leading to:

1. **Duplicate entries** (e.g., "Tokenizer-free embeddings" appears twice)
2. **Near-duplicates** with slightly different phrasing (e.g., multiple KAN entries)
3. **Ephemeral facts treated as permanent** (e.g., "ate a banana" stored forever)
4. **Core facts buried** among trivia (user's name mixed with paper summaries)
5. **Linear growth** with no consolidation or forgetting

Current state: 107 lines in `memory/notes.md` with visible redundancy.

---

## Design Goals

1. **Core Notes** - A compact, curated set of crucial information that persists indefinitely
2. **Working Memory** - Ephemeral facts that can be forgotten over time
3. **Semantic Deduplication** - Consolidate similar entries automatically
4. **Importance Scoring** - Distinguish "user's name" from "ate a banana"
5. **Graceful Forgetting** - Remove stale, low-importance facts without manual intervention

---

## Architecture

### Two-Tier Memory Model

```
┌─────────────────────────────────────────────────────────┐
│                    CORE NOTES                           │
│  - User identity (name, location, role)                 │
│  - Project identities (Tau, QQ)                         │
│  - Long-term preferences                                │
│  - Persistent relationships                             │
│  └── Protected from forgetting                          │
└─────────────────────────────────────────────────────────┘
                          ↑
                   Promotion (manual or earned)
                          │
┌─────────────────────────────────────────────────────────┐
│                  WORKING MEMORY                         │
│  - Research topics being explored                       │
│  - Temporary facts from conversations                   │
│  - File contents summaries                              │
│  - Ongoing threads                                      │
│  └── Subject to decay and forgetting                    │
└─────────────────────────────────────────────────────────┘
                          │
                   Decay / Archive
                          ↓
┌─────────────────────────────────────────────────────────┐
│                    ARCHIVE                              │
│  - Forgotten notes (queryable but not injected)         │
│  - Historical reference                                 │
│  - Can be restored on demand                            │
└─────────────────────────────────────────────────────────┘
```

### Core Notes Categories

These categories are **protected from forgetting**:

| Category | Examples | Protection Level |
|----------|----------|------------------|
| Identity | User name, location, role, preferences | Never forget |
| Projects | Tau, QQ, active codebases | Never forget (unless explicitly removed) |
| Relationships | Key people, collaborators | High protection |
| System Config | Hardware, setup details | High protection |

### Working Memory Attributes

Each note in working memory gains additional metadata:

```python
{
    "content": str,           # The note text
    "section": str,           # Key Topics, Important Facts, etc.
    "importance": float,      # 0.0 - 1.0 score
    "access_count": int,      # How often retrieved in context
    "last_accessed": datetime,# Last time used in retrieval
    "created_at": datetime,   # When first added
    "decay_rate": float,      # How fast importance decays
    "embedding": List[float], # For semantic search
}
```

---

## Importance Scoring

### Initial Importance Assignment

When a note is created, assign importance based on:

| Signal | Weight | Description |
|--------|--------|-------------|
| Identity markers | +0.5 | Contains "I am", "my name", "I prefer", etc. |
| Project references | +0.3 | Mentions user's known projects |
| Specificity | +0.2 | Concrete facts vs. vague observations |
| User emphasis | +0.3 | User explicitly stated it's important |
| Recurrence | +0.2 | Topic mentioned multiple times |
| Section weight | varies | People & Entities: +0.2, Key Topics: +0.1 |

### Importance Decay Formula

```python
def decay_importance(note, days_since_access, days_since_creation):
    # Base decay rate (configurable per note)
    base_decay = note.decay_rate or 0.01

    # Access frequency bonus (0-0.5)
    access_bonus = min(0.5, note.access_count * 0.05)

    # Age penalty (older = less relevant)
    age_factor = 1.0 / (1 + days_since_creation * 0.01)

    # Staleness penalty (not accessed recently)
    staleness = days_since_access * base_decay

    # Final importance
    decayed = note.importance - staleness
    adjusted = (decayed + access_bonus) * age_factor

    return max(0.0, min(1.0, adjusted))
```

### Importance Thresholds

| Threshold | Action |
|-----------|--------|
| > 0.8 | Candidate for promotion to Core |
| 0.4 - 0.8 | Active working memory |
| 0.2 - 0.4 | Low priority, shown only if highly relevant |
| < 0.2 | Candidate for archival |
| < 0.05 | Automatically archived |

---

## Deduplication Strategy

### Semantic Similarity Detection

Run periodically (e.g., after every N conversations or daily):

```python
def find_duplicates(notes, similarity_threshold=0.85):
    duplicates = []
    for i, note_a in enumerate(notes):
        for note_b in notes[i+1:]:
            similarity = cosine_similarity(note_a.embedding, note_b.embedding)
            if similarity > similarity_threshold:
                duplicates.append((note_a, note_b, similarity))
    return duplicates
```

### Consolidation Rules

When duplicates are found:

1. **Keep the higher-importance note**
2. **Merge unique information** from the lower one
3. **Combine access counts** and timestamps
4. **Archive the duplicate** (don't delete immediately)

### Consolidation Prompt (LLM-assisted)

```
Given these similar notes:
1. "{note_a}"
2. "{note_b}"

Create a single consolidated note that:
- Preserves all unique information
- Uses precise, concise language
- Removes redundancy

Return only the consolidated note text.
```

---

## Implementation Plan

### Phase 1: Core Notes Foundation

**Files to create/modify:**

1. **`src/qq/memory/core_notes.py`** - Core notes manager
   ```python
   class CoreNotesManager:
       PROTECTED_SECTIONS = ["Identity", "Projects", "Relationships"]

       def add_core(self, content: str, category: str) -> bool
       def get_core_notes(self) -> List[CoreNote]
       def is_protected(self, note_id: str) -> bool
   ```

2. **`memory/core.md`** - New file for core notes
   ```markdown
   # Core Memory

   ## Identity
   - Preferred name: Ori
   - Full name: Ori Nachum
   - Location: Israel
   - Role: AI Expert

   ## Projects
   - Tau – AI system under development
   - QQ – This conversational agent

   ## System
   - Hardware: NVIDIA DGX Spark, Blackwell architecture
   ```

3. **Modify `src/qq/agents/notes/notes.py`**
   - Add importance scoring on extraction
   - Route high-importance items to core evaluation
   - Add decay_rate assignment

### Phase 2: Importance & Decay System

**Files to create/modify:**

1. **`src/qq/memory/importance.py`** - Importance scoring
   ```python
   class ImportanceScorer:
       IDENTITY_PATTERNS = [r"my name", r"I am", r"I prefer", ...]

       def score_note(self, content: str, section: str) -> float
       def decay_notes(self, notes: List[Note], current_time: datetime)
       def get_archival_candidates(self, threshold=0.05) -> List[Note]
   ```

2. **Modify `src/qq/memory/mongo_store.py`**
   - Add fields: `importance`, `access_count`, `last_accessed`, `decay_rate`
   - Add `increment_access()` method
   - Add `get_by_importance_range()` method

3. **Modify `src/qq/context/retrieval_agent.py`**
   - Increment `access_count` when notes are retrieved
   - Update `last_accessed` timestamp
   - Filter by minimum importance threshold

### Phase 3: Deduplication & Consolidation

**Files to create/modify:**

1. **`src/qq/memory/deduplication.py`** - Duplicate detection
   ```python
   class NoteDeduplicator:
       def find_similar(self, threshold=0.85) -> List[Tuple[Note, Note]]
       def consolidate(self, note_a: Note, note_b: Note) -> Note
       def run_consolidation_pass(self) -> ConsolidationReport
   ```

2. **`src/qq/agents/consolidation/`** - New agent for LLM-assisted merging
   - `consolidation.system.md` - System prompt
   - `consolidation.user.md` - User prompt template
   - `consolidation.py` - Agent implementation

3. **Scheduled task** - Run deduplication periodically
   - After backup (already runs daily)
   - Or after every N conversations

### Phase 4: Archive System

**Files to create/modify:**

1. **`src/qq/memory/archive.py`** - Archive manager
   ```python
   class ArchiveManager:
       def archive_note(self, note_id: str, reason: str)
       def restore_note(self, note_id: str)
       def search_archive(self, query: str) -> List[ArchivedNote]
       def purge_old_archives(self, days=90)
   ```

2. **`memory/archive.jsonl`** - Archived notes storage
   - JSONL format for append-only writes
   - Includes reason for archival and timestamp

3. **New skill: `/memory-restore`**
   - Allow user to search and restore archived notes

### Phase 5: Migration & Cleanup

1. **Migration script** - One-time cleanup of existing notes
   ```python
   def migrate_notes():
       # 1. Load all current notes
       # 2. Score importance for each
       # 3. Identify and promote core notes
       # 4. Run deduplication
       # 5. Archive low-importance items
       # 6. Rebuild notes.md with remaining items
   ```

2. **Update `notes.user.md`** prompt
   - Add importance classification instruction
   - Add duplicate detection hint
   - Add core note identification

---

## File Structure After Implementation

```
src/qq/
├── memory/
│   ├── notes.py           # Modified: delegates to core/working
│   ├── core_notes.py      # NEW: Core notes manager
│   ├── importance.py      # NEW: Scoring and decay
│   ├── deduplication.py   # NEW: Duplicate detection
│   ├── archive.py         # NEW: Archive management
│   └── mongo_store.py     # Modified: new fields
├── agents/
│   ├── notes/
│   │   ├── notes.py       # Modified: importance scoring
│   │   └── notes.user.md  # Modified: new instructions
│   └── consolidation/     # NEW: Consolidation agent
│       ├── consolidation.py
│       ├── consolidation.system.md
│       └── consolidation.user.md
└── context/
    └── retrieval_agent.py # Modified: access tracking

memory/
├── notes.md               # Working memory (smaller)
├── core.md                # NEW: Core notes (protected)
└── archive.jsonl          # NEW: Archived notes
```

---

## Configuration

New environment variables:

```bash
# Importance thresholds
QQ_CORE_THRESHOLD=0.8        # Minimum importance for core promotion
QQ_ARCHIVE_THRESHOLD=0.05    # Below this, auto-archive
QQ_MIN_RETRIEVAL_IMPORTANCE=0.2  # Don't retrieve below this

# Decay settings
QQ_BASE_DECAY_RATE=0.01      # Daily importance decay
QQ_DEDUP_THRESHOLD=0.85      # Similarity threshold for duplicates

# Limits
QQ_MAX_WORKING_NOTES=100     # Max notes before forced consolidation
QQ_ARCHIVE_RETENTION_DAYS=90 # Days before archived notes are purged
```

---

## Updated Extraction Prompt

Modify `notes.user.md` to include importance classification:

```markdown
For each addition, also classify importance:

Importance levels:
- "core": User identity, preferences, projects (name, location, role)
- "high": Specific decisions, important facts, key relationships
- "medium": Research topics, ongoing investigations
- "low": Temporary observations, single-mention facts

Response format:
{
  "additions": [
    {"section": "...", "item": "...", "importance": "high"}
  ],
  "removals": ["..."],
  "summary": "..."
}
```

---

## Maintenance Commands

New CLI commands / skills:

| Command | Description |
|---------|-------------|
| `qq-memory --consolidate` | Run deduplication pass |
| `qq-memory --decay` | Apply decay to all notes |
| `qq-memory --archive` | Archive low-importance notes |
| `qq-memory --core` | Show core notes |
| `/memory-promote <item>` | Promote a note to core |
| `/memory-forget <item>` | Force-archive a note |
| `/memory-restore <query>` | Search and restore from archive |

---

## Success Metrics

After implementation:

1. **Notes.md size** should stabilize around 50-80 items (vs. unbounded growth)
2. **Core.md** should contain 10-20 crucial facts
3. **Duplicate rate** should drop to <5% (from current ~15%)
4. **User identity retrieval** should be 100% reliable
5. **Context injection quality** should improve (higher signal-to-noise)

---

## Risks & Mitigations

| Risk | Mitigation |
|------|------------|
| Over-aggressive forgetting | Conservative thresholds, archive before delete |
| Important note archived | Easy restore via `/memory-restore` |
| Consolidation loses info | LLM-assisted merge preserves details |
| Performance overhead | Run maintenance during backup (already scheduled) |
| Migration breaks existing notes | Backup before migration, reversible |

---

## Timeline

| Phase | Dependencies | Effort |
|-------|--------------|--------|
| Phase 1: Core Notes | None | Foundation |
| Phase 2: Importance | Phase 1 | Core feature |
| Phase 3: Deduplication | Phase 2 | Core feature |
| Phase 4: Archive | Phases 1-3 | Enhancement |
| Phase 5: Migration | Phases 1-4 | Cleanup |

---

## Current Notes Analysis

From `memory/notes.md` (107 lines):

### Identified Duplicates (should be consolidated)
- Lines 11-12: "Tokenizer-free embeddings" (exact duplicate)
- Lines 10, 13: Large Concept Models (near-duplicate)
- Lines 16, 25, 26: KAN entries (overlapping content)
- Lines 40, 41, 45: Table Understanding Benchmark (3 versions)
- Lines 21, 22, 24: Multi-step retrieval / KG-RAG (similar)
- Lines 59, 90, 93: Ori identity (fragmented across sections)

### Core Note Candidates (should be protected)
- Line 59: "Preferred name: Ori"
- Line 94: "Ori Nachum – user's full name"
- Line 81: "User's role: AI Expert"
- Line 83: "Location: Israel"
- Line 82: "Hardware: NVIDIA DGX Spark..."
- Line 54: "Tau project – AI system being built by Ori"

### Archive Candidates (low importance, stale)
- Lines 35-39: Generic benchmark findings (low specificity)
- Lines 70-73: Generic empirical results without context

---

## Next Steps

1. Review and approve this plan
2. Create `memory/core.md` with manually curated core notes
3. Implement Phase 1 (CoreNotesManager)
4. Run initial migration to consolidate duplicates
5. Iterate on importance scoring based on real usage
