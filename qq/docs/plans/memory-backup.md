# Memory Backup System Plan

**Created:** 2026-02-04
**Status:** Draft
**Related:** [Persistence Investigation](../investigations/persistence-memory.md)

## Overview

Implement a unified backup system for QQ's memory stores:
- **notes.md** - Markdown file with structured notes
- **MongoDB** - Notes with vector embeddings (qq_memory.notes collection)
- **Neo4j** - Knowledge graph (entities and relationships)

## Requirements

### Backup Triggers

| Trigger | Description |
|---------|-------------|
| First interaction of day | Automatic backup before first conversation turn each calendar day |
| Ad-hoc request | User explicitly requests backup via CLI or command |
| Cleanup | Retention policy keeps one backup per week, deletes older ones |

### Backup Contents

Each backup captures **core data only** - embeddings are excluded (regenerable from content).

```
backups/
├── 2026-02-04_093015/          # YYYY-MM-DD_HHMMSS timestamp
│   ├── manifest.json           # Backup metadata (small, JSON ok)
│   ├── notes.md                # Copy of notes file
│   ├── mongodb_notes.jsonl     # MongoDB notes (JSONL, no embeddings)
│   └── neo4j_graph.jsonl       # Neo4j entities + relationships (JSONL)
├── 2026-02-03_081230/
│   └── ...
└── .last_backup                # Tracks last backup date for daily trigger
```

### Scalability Design Principles

| Principle | Implementation |
|-----------|----------------|
| **No embeddings** | Exclude `embedding` field - regenerate on restore |
| **JSONL format** | One record per line - stream read/write, no full load |
| **Core data only** | Content, metadata, relationships - not derived indexes |
| **Lazy restore** | Restore notes immediately, queue embedding regeneration |

---

## Implementation Plan

### Phase 1: Core Backup Manager

**File:** `src/qq/backup/manager.py`

```python
class BackupManager:
    """
    Unified backup manager for all QQ memory stores.

    Handles:
    - Creating timestamped backup snapshots
    - Tracking last backup date for daily trigger
    - Cleanup based on retention policy
    """

    def __init__(self, backup_dir: Optional[str] = None):
        self.backup_dir = Path(backup_dir or os.getenv("QQ_BACKUP_DIR", "./backups"))
        self.last_backup_file = self.backup_dir / ".last_backup"

    def should_backup_today(self) -> bool:
        """Check if backup needed (first interaction of day)."""

    def create_backup(self) -> str:
        """Create full backup snapshot, return backup path."""

    def cleanup_old_backups(self) -> int:
        """Apply retention policy, return deleted count."""

    def list_backups(self) -> List[BackupInfo]:
        """List all available backups."""

    def restore_backup(self, backup_id: str) -> bool:
        """Restore from a specific backup."""
```

### Phase 2: Individual Store Backup Functions

**File:** `src/qq/backup/stores.py`

#### 2.1 Notes Backup

```python
def backup_notes(backup_path: Path) -> dict:
    """
    Backup notes.md file.

    Returns:
        {"success": True, "file": "notes.md", "size": 1234}
    """
    from qq.memory.notes import NotesManager

    manager = NotesManager()
    content = manager.get_notes()

    dest = backup_path / "notes.md"
    dest.write_text(content)

    return {"success": True, "file": "notes.md", "size": len(content)}
```

#### 2.2 MongoDB Backup

```python
def backup_mongodb(backup_path: Path) -> dict:
    """
    Export MongoDB notes collection to JSONL (streaming format).

    - Excludes embeddings (regenerable from content)
    - Writes one document per line (no full collection in memory)
    - Preserves: note_id, content, section, metadata, updated_at

    Returns:
        {"success": True, "file": "mongodb_notes.jsonl", "count": 42}
    """
    from pymongo import MongoClient
    import json

    uri = os.getenv("MONGODB_URI", "mongodb://localhost:27017")
    client = MongoClient(uri, serverSelectionTimeoutMS=5000)

    db = client["qq_memory"]
    dest = backup_path / "mongodb_notes.jsonl"
    count = 0

    # Stream write - never load full collection
    with open(dest, 'w') as f:
        for doc in db["notes"].find({}, {"embedding": 0}):  # Exclude embeddings
            record = {
                "note_id": doc.get("note_id"),
                "content": doc.get("content"),
                "section": doc.get("section"),
                "metadata": doc.get("metadata", {}),
                "updated_at": doc["updated_at"].isoformat() if doc.get("updated_at") else None,
            }
            f.write(json.dumps(record) + "\n")
            count += 1

    return {"success": True, "file": "mongodb_notes.jsonl", "count": count}
```

**JSONL advantages:**
- Stream processing: Read/write line by line
- Memory efficient: O(1) memory vs O(n) for JSON array
- Append-friendly: Can add records without rewriting
- Grep-able: Search with standard unix tools

#### 2.3 Neo4j Backup

```python
def backup_neo4j(backup_path: Path) -> dict:
    """
    Export Neo4j graph to JSONL (streaming format).

    - Excludes embeddings (regenerable from name + description)
    - Writes nodes first, then relationships
    - Each line is self-contained record with type marker

    Returns:
        {"success": True, "file": "neo4j_graph.jsonl", "nodes": 10, "rels": 5}
    """
    from neo4j import GraphDatabase
    import json

    driver = GraphDatabase.driver(
        os.getenv("NEO4J_URI", "bolt://localhost:7687"),
        auth=(os.getenv("NEO4J_USER", "neo4j"), os.getenv("NEO4J_PASSWORD", "refinerypass"))
    )

    dest = backup_path / "neo4j_graph.jsonl"
    node_count = 0
    rel_count = 0

    with open(dest, 'w') as f, driver.session() as session:
        # Stream nodes
        result = session.run("""
            MATCH (n)
            RETURN labels(n) as labels, properties(n) as props
        """)
        for record in result:
            props = record["props"]
            # Exclude embedding - will regenerate on restore
            node_record = {
                "_type": "node",
                "labels": record["labels"],
                "name": props.get("name"),
                "description": props.get("description"),
                # Include other properties except embedding
                "properties": {k: v for k, v in props.items()
                              if k not in ("embedding", "name", "description")}
            }
            f.write(json.dumps(node_record) + "\n")
            node_count += 1

        # Stream relationships
        result = session.run("""
            MATCH (a)-[r]->(b)
            RETURN a.name as source, b.name as target,
                   type(r) as rel_type, properties(r) as props
        """)
        for record in result:
            rel_record = {
                "_type": "relationship",
                "source": record["source"],
                "target": record["target"],
                "rel_type": record["rel_type"],
                "properties": record["props"] or {}
            }
            f.write(json.dumps(rel_record) + "\n")
            rel_count += 1

    driver.close()

    return {"success": True, "file": "neo4j_graph.jsonl", "nodes": node_count, "rels": rel_count}
```

**JSONL record format:**
```jsonl
{"_type": "node", "labels": ["Person"], "name": "Alice", "description": "Engineer"}
{"_type": "node", "labels": ["Concept"], "name": "Python", "description": "Programming language"}
{"_type": "relationship", "source": "Alice", "target": "Python", "rel_type": "KNOWS", "properties": {}}
```

### Phase 3: Manifest and Metadata

**File:** `src/qq/backup/manifest.py`

```python
@dataclass
class BackupManifest:
    """Backup metadata stored in manifest.json."""

    backup_id: str              # YYYY-MM-DD_HHMMSS
    created_at: datetime
    trigger: str                # "daily" | "manual" | "scheduled"

    notes: dict                 # {success, file, size}
    mongodb: dict               # {success, file, count} or {success: False, error: str}
    neo4j: dict                 # {success, file, nodes, rels} or {success: False, error: str}

    qq_version: str             # For compatibility checking

    def to_json(self) -> str:
        """Serialize to JSON."""

    @classmethod
    def from_json(cls, data: str) -> "BackupManifest":
        """Deserialize from JSON."""
```

**Example manifest.json:**
```json
{
  "backup_id": "2026-02-04_093015",
  "created_at": "2026-02-04T09:30:15.123456",
  "trigger": "daily",
  "format_version": "2",
  "notes": {
    "success": true,
    "file": "notes.md",
    "size_bytes": 2048
  },
  "mongodb": {
    "success": true,
    "file": "mongodb_notes.jsonl",
    "count": 42,
    "embeddings_excluded": true
  },
  "neo4j": {
    "success": true,
    "file": "neo4j_graph.jsonl",
    "nodes": 15,
    "rels": 8,
    "embeddings_excluded": true
  },
  "qq_version": "0.1.0"
}
```

### Phase 4: Daily Backup Trigger

**Integration point:** `src/qq/app.py` main() function

```python
def main() -> None:
    # ... existing setup ...

    # Check for daily backup (before first interaction)
    from qq.backup.manager import BackupManager

    backup_manager = BackupManager()
    if backup_manager.should_backup_today():
        if args.verbose:
            console.print_info("Creating daily memory backup...")
        try:
            backup_path = backup_manager.create_backup(trigger="daily")
            if args.verbose:
                console.print_info(f"Backup created: {backup_path}")
        except Exception as e:
            console.print_warning(f"Backup failed: {e}")

    # ... rest of main() ...
```

**Last backup tracking:**

```python
def should_backup_today(self) -> bool:
    """Check if we need to create a daily backup."""
    if not self.last_backup_file.exists():
        return True

    last_backup_date = self.last_backup_file.read_text().strip()
    today = datetime.now().strftime("%Y-%m-%d")

    return last_backup_date != today

def _mark_backup_done(self) -> None:
    """Update last backup marker."""
    self.backup_dir.mkdir(parents=True, exist_ok=True)
    self.last_backup_file.write_text(datetime.now().strftime("%Y-%m-%d"))
```

### Phase 5: CLI Commands

**File:** `src/qq/backup/cli.py`

**Entry point:** Add to `pyproject.toml`
```toml
[project.scripts]
qq-backup = "qq.backup.cli:main"
```

**CLI Interface:**

```
qq-backup                   # Create backup now
qq-backup --list            # List all backups
qq-backup --restore <id>    # Restore from backup
qq-backup --cleanup         # Run retention cleanup
qq-backup --status          # Show backup status
```

**Implementation:**

```python
def main():
    parser = argparse.ArgumentParser(description="QQ Memory Backup")
    parser.add_argument("--list", action="store_true", help="List backups")
    parser.add_argument("--restore", metavar="ID", help="Restore backup by ID")
    parser.add_argument("--cleanup", action="store_true", help="Run cleanup")
    parser.add_argument("--status", action="store_true", help="Show status")
    parser.add_argument("--dry-run", action="store_true", help="Preview without changes")

    args = parser.parse_args()
    manager = BackupManager()

    if args.list:
        cmd_list(manager)
    elif args.restore:
        cmd_restore(manager, args.restore, args.dry_run)
    elif args.cleanup:
        cmd_cleanup(manager, args.dry_run)
    elif args.status:
        cmd_status(manager)
    else:
        # Default: create backup
        cmd_create(manager)
```

### Phase 6: Retention Policy and Cleanup

**Algorithm:** Keep one backup per week, delete older

```python
def cleanup_old_backups(self, dry_run: bool = False) -> List[str]:
    """
    Apply retention policy:
    - Keep all backups from current week
    - Keep one backup per previous week (Sunday or earliest)
    - Delete rest

    Returns list of deleted backup IDs.
    """
    backups = self.list_backups()
    if not backups:
        return []

    # Group by ISO week
    by_week: Dict[str, List[BackupInfo]] = defaultdict(list)
    for backup in backups:
        week_key = backup.created_at.strftime("%Y-W%W")
        by_week[week_key].append(backup)

    current_week = datetime.now().strftime("%Y-W%W")
    to_delete = []

    for week, week_backups in by_week.items():
        if week == current_week:
            # Keep all from current week
            continue

        # Sort by date, keep oldest (typically Sunday)
        week_backups.sort(key=lambda b: b.created_at)

        # Delete all but first
        for backup in week_backups[1:]:
            to_delete.append(backup.backup_id)

    if not dry_run:
        for backup_id in to_delete:
            self._delete_backup(backup_id)

    return to_delete
```

**Cleanup scheduling options:**

1. **On backup creation** - Run cleanup after each new backup
2. **Weekly cron** - External scheduler runs `qq-backup --cleanup`
3. **Manual** - User runs cleanup when needed

Recommendation: Run cleanup automatically after daily backup.

### Phase 7: Console Command Integration

Add backup command to console mode:

```python
# In run_console_mode()
if user_input.lower() == "backup":
    from qq.backup.manager import BackupManager
    manager = BackupManager()
    backup_path = manager.create_backup(trigger="manual")
    console.print_info(f"Backup created: {backup_path}")
    continue
```

---

## File Structure

```
src/qq/backup/
├── __init__.py
├── manager.py      # BackupManager class
├── stores.py       # Individual store backup functions (JSONL streaming)
├── manifest.py     # BackupManifest dataclass
├── restore.py      # Restore functions with embedding regeneration
└── cli.py          # qq-backup CLI entry point

Backup output:
backups/<timestamp>/
├── manifest.json       # 1-2 KB metadata
├── notes.md            # Same as source
├── mongodb_notes.jsonl # ~500 bytes per note (no embeddings)
└── neo4j_graph.jsonl   # ~200 bytes per entity/relationship
```

---

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `QQ_BACKUP_DIR` | `./backups` | Backup storage directory |
| `QQ_BACKUP_RETENTION_WEEKS` | `4` | Weeks to retain weekly backups |
| `QQ_BACKUP_ENABLED` | `true` | Enable/disable automatic backups |

---

## Error Handling

### Partial Backup Success

If one store fails, continue with others and mark in manifest:

```python
def create_backup(self, trigger: str = "manual") -> str:
    backup_id = datetime.now().strftime("%Y-%m-%d_%H%M%S")
    backup_path = self.backup_dir / backup_id
    backup_path.mkdir(parents=True, exist_ok=True)

    manifest = BackupManifest(
        backup_id=backup_id,
        created_at=datetime.now(),
        trigger=trigger,
    )

    # Notes (always available)
    manifest.notes = backup_notes(backup_path)

    # MongoDB (may be unavailable)
    try:
        manifest.mongodb = backup_mongodb(backup_path)
    except Exception as e:
        manifest.mongodb = {"success": False, "error": str(e)}

    # Neo4j (may be unavailable)
    try:
        manifest.neo4j = backup_neo4j(backup_path)
    except Exception as e:
        manifest.neo4j = {"success": False, "error": str(e)}

    # Save manifest
    (backup_path / "manifest.json").write_text(manifest.to_json())

    # Mark daily backup done
    if trigger == "daily":
        self._mark_backup_done()

    return str(backup_path)
```

### Restore Safety

Restore operations should:
1. Create a backup of current state first
2. Validate backup integrity before restoring
3. Support partial restore (notes only, mongo only, etc.)

### Restore with Embedding Regeneration

**File:** `src/qq/backup/restore.py`

```python
def restore_mongodb(backup_path: Path, embeddings: EmbeddingClient) -> dict:
    """
    Restore MongoDB from JSONL backup with streaming read.

    - Reads line by line (constant memory)
    - Regenerates embeddings for each note
    - Uses upsert to avoid duplicates
    """
    from pymongo import MongoClient

    client = MongoClient(os.getenv("MONGODB_URI", "mongodb://localhost:27017"))
    collection = client["qq_memory"]["notes"]

    jsonl_file = backup_path / "mongodb_notes.jsonl"
    count = 0
    embedding_errors = 0

    with open(jsonl_file, 'r') as f:
        for line in f:
            record = json.loads(line.strip())

            # Regenerate embedding from content
            embedding = []
            if record.get("content") and embeddings:
                try:
                    embedding = embeddings.get_embedding(record["content"])
                except Exception:
                    embedding_errors += 1

            # Upsert to collection
            collection.update_one(
                {"note_id": record["note_id"]},
                {"$set": {
                    "note_id": record["note_id"],
                    "content": record["content"],
                    "section": record.get("section"),
                    "metadata": record.get("metadata", {}),
                    "embedding": embedding,
                    "updated_at": datetime.fromisoformat(record["updated_at"])
                        if record.get("updated_at") else datetime.utcnow(),
                }},
                upsert=True
            )
            count += 1

    return {"restored": count, "embedding_errors": embedding_errors}


def restore_neo4j(backup_path: Path, embeddings: EmbeddingClient) -> dict:
    """
    Restore Neo4j from JSONL backup with streaming read.

    - Pass 1: Create all nodes with embeddings
    - Pass 2: Create all relationships
    """
    from neo4j import GraphDatabase

    driver = GraphDatabase.driver(
        os.getenv("NEO4J_URI", "bolt://localhost:7687"),
        auth=(os.getenv("NEO4J_USER", "neo4j"), os.getenv("NEO4J_PASSWORD", "refinerypass"))
    )

    jsonl_file = backup_path / "neo4j_graph.jsonl"
    nodes = 0
    rels = 0

    with driver.session() as session:
        # Pass 1: Nodes
        with open(jsonl_file, 'r') as f:
            for line in f:
                record = json.loads(line.strip())
                if record["_type"] != "node":
                    continue

                # Regenerate embedding
                embedding = None
                if embeddings and record.get("name"):
                    try:
                        embed_text = f"{record['name']}: {record.get('description', '')}"
                        embedding = embeddings.get_embedding(embed_text)
                    except Exception:
                        pass

                labels = ":".join(record["labels"])
                props = {
                    "name": record["name"],
                    "description": record.get("description"),
                    **record.get("properties", {})
                }
                if embedding:
                    props["embedding"] = embedding

                session.run(
                    f"MERGE (n:{labels} {{name: $name}}) SET n = $props",
                    {"name": record["name"], "props": props}
                )
                nodes += 1

        # Pass 2: Relationships
        with open(jsonl_file, 'r') as f:
            for line in f:
                record = json.loads(line.strip())
                if record["_type"] != "relationship":
                    continue

                session.run(
                    f"""MATCH (a {{name: $source}}), (b {{name: $target}})
                        MERGE (a)-[r:{record['rel_type']}]->(b)
                        SET r = $props""",
                    {
                        "source": record["source"],
                        "target": record["target"],
                        "props": record.get("properties", {})
                    }
                )
                rels += 1

    driver.close()
    return {"nodes": nodes, "relationships": rels}
```

**Restore CLI:**
```bash
qq-backup --restore 2026-02-04_093015              # Full restore
qq-backup --restore 2026-02-04_093015 --notes-only # Notes.md only
qq-backup --restore 2026-02-04_093015 --skip-embeddings  # Skip regeneration (fast)
```

---

## Implementation Order

1. **Week 1: Core Infrastructure**
   - [ ] Create `src/qq/backup/` package
   - [ ] Implement `BackupManager` class
   - [ ] Implement `backup_notes()` function
   - [ ] Add manifest handling

2. **Week 2: Database Backups**
   - [ ] Implement `backup_mongodb()` function
   - [ ] Implement `backup_neo4j()` function
   - [ ] Add error handling for unavailable services

3. **Week 3: CLI and Integration**
   - [ ] Create `qq-backup` CLI tool
   - [ ] Integrate daily backup into `app.py`
   - [ ] Add `backup` console command

4. **Week 4: Cleanup and Polish**
   - [ ] Implement retention policy cleanup
   - [ ] Add restore functionality
   - [ ] Add tests
   - [ ] Documentation

---

## Testing Strategy

### Unit Tests

```python
# tests/backup/test_manager.py

def test_should_backup_today_first_run():
    """First run should trigger backup."""
    manager = BackupManager(backup_dir=tmp_path)
    assert manager.should_backup_today() is True

def test_should_backup_today_already_done():
    """Same day should not trigger."""
    manager = BackupManager(backup_dir=tmp_path)
    manager._mark_backup_done()
    assert manager.should_backup_today() is False

def test_cleanup_retention():
    """Verify weekly retention keeps correct backups."""
    # Create backups spanning 3 weeks
    # Run cleanup
    # Verify one per week kept
```

### Integration Tests

```python
def test_full_backup_cycle():
    """Test backup and restore cycle."""
    # 1. Populate memory stores with test data
    # 2. Create backup
    # 3. Clear stores
    # 4. Restore backup
    # 5. Verify data matches
```

---

## Future Enhancements

1. **Compression** - gzip JSONL files (typically 5-10x reduction on text)
2. **Encryption** - Encrypt backups containing sensitive data
3. **Remote storage** - Sync backups to S3/GCS
4. **Incremental backups** - Track changes via `updated_at`, backup only deltas
5. **Async embedding regeneration** - Queue background job for embeddings on restore
6. **Scheduled backups** - Integration with system cron or internal scheduler
7. **Batch embedding API** - Send multiple texts in one request for faster restore

---

## Appendix A: Size Estimates

**Embedding impact (typical 384-dim float32 vectors):**

| Records | With Embeddings | Without Embeddings | Savings |
|---------|-----------------|-------------------|---------|
| 100     | ~600 KB         | ~50 KB            | 92%     |
| 1,000   | ~6 MB           | ~500 KB           | 92%     |
| 10,000  | ~60 MB          | ~5 MB             | 92%     |
| 100,000 | ~600 MB         | ~50 MB            | 92%     |

**JSONL vs JSON memory usage during backup:**

| Format | 10K records | Memory during write |
|--------|-------------|---------------------|
| JSON   | 5 MB file   | 5 MB (full array)   |
| JSONL  | 5 MB file   | ~1 KB (one line)    |

## Appendix B: JSONL Format Specification

**MongoDB notes backup:**
```jsonl
{"note_id": "a1b2c3", "content": "User prefers dark mode", "section": "Key Topics", "metadata": {}, "updated_at": "2026-02-04T09:30:00"}
{"note_id": "d4e5f6", "content": "Project uses Python 3.12", "section": "Important Facts", "metadata": {}, "updated_at": "2026-02-04T09:31:00"}
```

**Neo4j graph backup:**
```jsonl
{"_type": "node", "labels": ["Person"], "name": "Alice", "description": "Software engineer", "properties": {}}
{"_type": "node", "labels": ["Concept"], "name": "Python", "description": "Programming language", "properties": {}}
{"_type": "relationship", "source": "Alice", "target": "Python", "rel_type": "KNOWS", "properties": {"since": "2020"}}
```

**Benefits:**
- `grep "Alice" neo4j_graph.jsonl` - Search without parsing
- `wc -l mongodb_notes.jsonl` - Count records instantly
- `head -100 mongodb_notes.jsonl` - Preview without loading all
- Append new records without rewriting file
