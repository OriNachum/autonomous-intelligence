"""qq-memory - CLI tool to peek into memory status and run maintenance."""

import os
import sys
from datetime import datetime


def get_core_notes_snapshot():
    """Get the core.md content."""
    from qq.memory.core_notes import CoreNotesManager

    try:
        manager = CoreNotesManager()
        return manager.get_notes()
    except Exception as e:
        return f"Error loading core notes: {e}"


def get_notes_snapshot():
    """Get the notes.md content."""
    from qq.memory.notes import NotesManager
    
    try:
        manager = NotesManager()
        return manager.get_notes()
    except Exception as e:
        return f"Error loading notes: {e}"


def get_mongo_stats():
    """Get MongoDB record count and status."""
    try:
        from pymongo import MongoClient
        
        uri = os.getenv("MONGODB_URI", "mongodb://localhost:27017")
        client = MongoClient(uri, serverSelectionTimeoutMS=2000)
        
        # Force connection check
        client.admin.command('ping')
        
        db = client["qq_memory"]
        notes_count = db["notes"].count_documents({})
        
        # Get sample notes
        sample_notes = list(db["notes"].find({}, {"content": 1, "section": 1}).limit(5))
        
        return {
            "status": "connected",
            "count": notes_count,
            "samples": [
                {"section": n.get("section", ""), "content": n.get("content", "")[:100]}
                for n in sample_notes
            ]
        }
    except Exception as e:
        return {"status": "disconnected", "error": str(e), "count": 0}


def get_neo4j_stats():
    """Get Neo4j record count and status."""
    try:
        from neo4j import GraphDatabase
        
        uri = os.getenv("NEO4J_URI", "bolt://localhost:7687")
        user = os.getenv("NEO4J_USER", "neo4j")
        password = os.getenv("NEO4J_PASSWORD", "refinerypass")
        
        driver = GraphDatabase.driver(uri, auth=(user, password))
        
        with driver.session() as session:
            # Count all nodes
            result = session.run("MATCH (n) RETURN count(n) as count")
            node_count = result.single()["count"]
            
            # Count relationships
            result = session.run("MATCH ()-[r]->() RETURN count(r) as count")
            rel_count = result.single()["count"]
            
            # Get entity type breakdown
            result = session.run(
                "MATCH (n) RETURN labels(n)[0] as type, count(n) as count ORDER BY count DESC LIMIT 5"
            )
            types = [(r["type"], r["count"]) for r in result]
        
        driver.close()
        
        return {
            "status": "connected",
            "node_count": node_count,
            "relationship_count": rel_count,
            "entity_types": types,
        }
    except Exception as e:
        return {"status": "disconnected", "error": str(e), "node_count": 0, "relationship_count": 0}


def run_consolidation():
    """Run deduplication/consolidation pass on notes."""
    from qq.memory.deduplication import NoteDeduplicator
    from qq.memory.archive import ArchiveManager

    print("Running consolidation pass...")

    try:
        deduplicator = NoteDeduplicator()
        archive_manager = ArchiveManager()

        report = deduplicator.run_consolidation_pass(archive_manager=archive_manager)

        print(f"\nConsolidation Report:")
        print(f"  Duplicates found: {report.duplicates_found}")
        print(f"  Notes merged: {report.notes_merged}")
        print(f"  Notes archived: {report.notes_archived}")
        print(f"  Original count: {report.original_count}")
        print(f"  Final count: {report.final_count}")
        print(f"  Timestamp: {report.timestamp}")

        return report
    except Exception as e:
        print(f"Error during consolidation: {e}")
        return None


def run_decay():
    """Apply importance decay to all notes."""
    from qq.memory.mongo_store import MongoNotesStore
    from qq.memory.importance import ImportanceScorer, ScoredNote

    print("Applying importance decay...")

    try:
        store = MongoNotesStore()
        scorer = ImportanceScorer()

        # Get all notes
        notes = list(store.collection.find({}))
        updates = []

        for note in notes:
            scored = ScoredNote(
                content=note.get("content", ""),
                section=note.get("section", ""),
                importance=note.get("importance", 0.5),
                access_count=note.get("access_count", 0),
                last_accessed=note.get("last_accessed"),
                created_at=note.get("created_at", datetime.now()),
                note_id=note.get("note_id"),
            )

            decayed = scorer.decay_importance(scored)

            if abs(decayed - scored.importance) > 0.001:
                updates.append({
                    "note_id": scored.note_id,
                    "importance": decayed,
                })

        if updates:
            count = store.bulk_update_importance(updates)
            print(f"Updated importance for {count} notes")
        else:
            print("No importance changes needed")

        return len(updates)
    except Exception as e:
        print(f"Error during decay: {e}")
        return 0


def run_archive(threshold: float = 0.05):
    """Archive low-importance notes."""
    from qq.memory.archive import ArchiveManager

    print(f"Archiving notes below importance {threshold}...")

    try:
        archive_manager = ArchiveManager()
        count = archive_manager.archive_low_importance(threshold=threshold)
        print(f"Archived {count} notes")
        return count
    except Exception as e:
        print(f"Error during archival: {e}")
        return 0


def run_cleanup(max_items: int = 50):
    """
    Clean up notes.md by:
    1. Removing items that belong in core.md (identity, user info)
    2. Removing exact and near-duplicates
    3. Keeping only the most important items up to max_items
    """
    import re
    from qq.memory.notes import NotesManager
    from qq.memory.core_notes import CoreNotesManager
    from qq.memory.importance import ImportanceScorer

    print(f"Cleaning up notes.md (max {max_items} items)...")

    # Patterns that indicate core/identity information (should be in core.md)
    CORE_PATTERNS = [
        r"^ori\b",                          # User's name
        r"\bori nachum\b",                  # Full name
        r"\buser'?s?\s+(name|role|full name)\b",  # User's X
        r"\bpreferred name\b",              # Preferred name
        r"^location:\s",                    # Location info
        r"^hardware:\s",                    # Hardware (already in core)
        r"^role:\s",                        # Role info
        r"\bi am\b.*\b(expert|developer|engineer)\b",
        r"^tau\s*(–|-)?\s*(project)?\b",    # User's Tau project
        r"\bby ori\b",                      # References to user
        r"\bdeveloped by ori\b",
    ]

    # Patterns for near-duplicate detection (normalize before comparing)
    def normalize_for_dedup(text: str) -> str:
        """Normalize text for duplicate detection."""
        text = text.lower().strip()
        # Remove common prefixes
        text = re.sub(r"^(the|a|an)\s+", "", text)
        # Remove punctuation
        text = re.sub(r"[^\w\s]", " ", text)
        # Collapse whitespace
        text = re.sub(r"\s+", " ", text)
        return text.strip()

    def is_near_duplicate(content: str, seen_normalized: set, threshold: float = 0.6) -> bool:
        """Check if content is a near-duplicate of something seen."""
        normalized = normalize_for_dedup(content)
        words = set(normalized.split())

        if not words:
            return True

        # Extract the first "entity" (first 1-3 words before a dash or colon)
        def get_entity_prefix(text: str) -> str:
            # Get text before common separators
            for sep in [' – ', ' - ', ' — ', ': ', ' author ', ' project ']:
                if sep in text:
                    return text.split(sep)[0].strip()
            return text.split()[0] if text.split() else ""

        entity_prefix = get_entity_prefix(normalized)

        for seen in seen_normalized:
            seen_words = set(seen.split())
            if not seen_words:
                continue

            # Jaccard similarity
            intersection = len(words & seen_words)
            union = len(words | seen_words)
            similarity = intersection / union if union > 0 else 0

            if similarity >= threshold:
                return True

            # Check if one is substring of other
            if normalized in seen or seen in normalized:
                return True

            # Check if entity prefixes match (catches "Mike" vs "Mike Erlihson")
            seen_entity = get_entity_prefix(seen)
            if entity_prefix and seen_entity:
                if entity_prefix == seen_entity:
                    return True
                # One prefix contains the other
                if entity_prefix in seen_entity or seen_entity in entity_prefix:
                    return True

        return False

    try:
        notes_manager = NotesManager()
        core_manager = CoreNotesManager()
        scorer = ImportanceScorer()

        # Get all current items
        all_items = notes_manager.get_all_items()
        original_count = len(all_items)
        print(f"  Current items: {original_count}")

        # Get core items to exclude (exact matches)
        core_items = core_manager.get_all_items()
        core_contents = set()
        for category, items in core_items.items():
            for item in items:
                core_contents.add(item.strip().lower())

        # Filter and score items
        seen_normalized = set()
        scored_items = []

        for item in all_items:
            content = item["item"].strip()
            content_lower = content.lower()

            # Skip if empty
            if not content:
                continue

            # Skip if matches core patterns (belongs in core.md)
            is_core_pattern = False
            for pattern in CORE_PATTERNS:
                if re.search(pattern, content_lower):
                    print(f"  [CORE] Removing (identity info): {content[:50]}...")
                    is_core_pattern = True
                    break
            if is_core_pattern:
                continue

            # Skip if already in core.md (exact match)
            if content_lower in core_contents:
                print(f"  [CORE] Removing (in core.md): {content[:50]}...")
                continue

            # Skip if near-duplicate
            if is_near_duplicate(content, seen_normalized):
                print(f"  [DUP] Removing near-duplicate: {content[:50]}...")
                continue

            seen_normalized.add(normalize_for_dedup(content))

            # Score importance
            importance = scorer.score_note(content, item["section"])
            scored_items.append({
                "section": item["section"],
                "item": content,
                "importance": importance,
            })

        # Sort by importance (highest first)
        scored_items.sort(key=lambda x: x["importance"], reverse=True)

        # Keep only top max_items
        kept_items = scored_items[:max_items]
        removed_count = len(scored_items) - len(kept_items)

        if removed_count > 0:
            print(f"  [LIMIT] Removing {removed_count} low-importance items")

        # Rebuild notes.md
        notes_manager.rebuild_with_items(kept_items)

        final_count = len(kept_items)
        print(f"\nCleanup complete:")
        print(f"  Original: {original_count} items")
        print(f"  Final: {final_count} items")
        print(f"  Removed: {original_count - final_count} items")

        return final_count

    except Exception as e:
        print(f"Error during cleanup: {e}")
        import traceback
        traceback.print_exc()
        return 0


def run_full_maintenance(max_items: int = 50):
    """Run all maintenance tasks in sequence."""
    print("=" * 50)
    print("Running full memory maintenance")
    print("=" * 50)

    print("\n[1/4] Applying importance decay...")
    run_decay()

    print("\n[2/4] Running consolidation...")
    run_consolidation()

    print("\n[3/4] Archiving low-importance notes...")
    run_archive()

    print("\n[4/4] Cleaning up notes.md...")
    run_cleanup(max_items)

    print("\n" + "=" * 50)
    print("Maintenance complete!")
    print("=" * 50)


def get_archive_stats():
    """Get archive statistics."""
    from qq.memory.archive import ArchiveManager

    try:
        manager = ArchiveManager()
        return manager.get_archive_stats()
    except Exception as e:
        return {"error": str(e)}


def main():
    """Main entry point for qq-memory CLI."""
    try:
        from rich.console import Console
        from rich.panel import Panel
        from rich.table import Table
        from rich.markdown import Markdown
        console = Console()
        use_rich = True
    except ImportError:
        use_rich = False

    # Parse arguments
    show_notes = "--notes" in sys.argv or len(sys.argv) == 1
    show_core = "--core" in sys.argv or len(sys.argv) == 1
    show_mongo = "--mongo" in sys.argv or len(sys.argv) == 1
    show_neo4j = "--neo4j" in sys.argv or len(sys.argv) == 1
    show_archive = "--archive-stats" in sys.argv
    show_help = "--help" in sys.argv or "-h" in sys.argv

    # Maintenance commands
    do_consolidate = "--consolidate" in sys.argv
    do_decay = "--decay" in sys.argv
    do_archive = "--archive" in sys.argv
    do_cleanup = "--cleanup" in sys.argv
    do_full = "--full" in sys.argv or "--maintain" in sys.argv

    # Parse max-items argument
    max_items = 50
    for arg in sys.argv:
        if arg.startswith("--max-items="):
            try:
                max_items = int(arg.split("=")[1])
            except ValueError:
                pass

    if show_help:
        print("""qq-memory - Peek into QQ's memory stores and run maintenance

Usage:
  qq-memory              Show all memory stores
  qq-memory --notes      Show notes.md snapshot only
  qq-memory --core       Show core.md snapshot only
  qq-memory --mongo      Show MongoDB stats only
  qq-memory --neo4j      Show Neo4j stats only
  qq-memory --archive-stats  Show archive statistics

Maintenance commands:
  qq-memory --consolidate  Run deduplication pass in MongoDB
  qq-memory --decay        Apply importance decay to all notes
  qq-memory --archive      Archive notes below importance threshold
  qq-memory --cleanup      Clean up notes.md (remove duplicates, limit size)
  qq-memory --full         Run ALL maintenance tasks in sequence
  qq-memory --max-items=N  Set max items to keep in notes.md (default: 50)

Examples:
  qq-memory --cleanup --max-items=30   Clean notes.md, keep top 30 items
  qq-memory --full --max-items=40      Full maintenance with 40 item limit

Environment variables:
  MEMORY_DIR             Directory for notes (default: ./memory)
  MONGODB_URI            MongoDB connection URI (default: mongodb://localhost:27017)
  NEO4J_URI              Neo4j Bolt URI (default: bolt://localhost:7687)
  QQ_MAX_WORKING_NOTES   Max notes before forced cleanup (default: 100)
  QQ_DEDUP_THRESHOLD     Similarity threshold for duplicates (default: 0.85)
  QQ_ARCHIVE_THRESHOLD   Importance below which to archive (default: 0.05)
  QQ_BASE_DECAY_RATE     Daily importance decay rate (default: 0.01)
""")
        return

    # Handle maintenance commands
    if do_full:
        run_full_maintenance(max_items)
        return

    if do_consolidate:
        run_consolidation()
        return

    if do_decay:
        run_decay()
        return

    if do_archive:
        run_archive()
        return

    if do_cleanup:
        run_cleanup(max_items)
        return
    
    if use_rich:
        console.print("[bold cyan]QQ Memory Snapshot[/bold cyan]\n")
    else:
        print("=== QQ Memory Snapshot ===\n")

    # Core Notes
    if show_core:
        if use_rich:
            core_notes = get_core_notes_snapshot()
            console.print(Panel(Markdown(core_notes), title="⭐ Core Memory (core.md)", expand=False))
            console.print()
        else:
            print("--- Core Memory (core.md) ---")
            print(get_core_notes_snapshot())
            print()

    # Working Notes
    if show_notes:
        if use_rich:
            notes = get_notes_snapshot()
            console.print(Panel(Markdown(notes), title="📝 Working Notes (notes.md)", expand=False))
            console.print()
        else:
            print("--- Working Notes (notes.md) ---")
            print(get_notes_snapshot())
            print()

    # Archive Stats
    if show_archive:
        archive_stats = get_archive_stats()
        if use_rich:
            if "error" not in archive_stats:
                table = Table(title="📦 Archive Statistics")
                table.add_column("Metric", style="cyan")
                table.add_column("Value", style="green")
                table.add_row("Total archived", str(archive_stats.get("total", 0)))
                table.add_row("Active (not restored)", str(archive_stats.get("active", 0)))
                table.add_row("Restored", str(archive_stats.get("restored", 0)))
                console.print(table)

                by_reason = archive_stats.get("by_reason", {})
                if by_reason:
                    reason_table = Table(title="By Reason")
                    reason_table.add_column("Reason", style="dim")
                    reason_table.add_column("Count", style="green")
                    for reason, count in by_reason.items():
                        reason_table.add_row(reason, str(count))
                    console.print(reason_table)
            else:
                console.print(Panel(f"[red]Error: {archive_stats['error']}[/red]", title="📦 Archive"))
            console.print()
        else:
            print("--- Archive Statistics ---")
            print(f"Total: {archive_stats.get('total', 0)}")
            print(f"Active: {archive_stats.get('active', 0)}")
            print(f"Restored: {archive_stats.get('restored', 0)}")
            print()
    
    # MongoDB
    if show_mongo:
        mongo_stats = get_mongo_stats()
        if use_rich:
            if mongo_stats["status"] == "connected":
                table = Table(title="🍃 MongoDB (qq_memory.notes)")
                table.add_column("Metric", style="cyan")
                table.add_column("Value", style="green")
                table.add_row("Status", "✅ Connected")
                table.add_row("Record Count", str(mongo_stats["count"]))
                console.print(table)
                
                if mongo_stats.get("samples"):
                    sample_table = Table(title="Sample Notes")
                    sample_table.add_column("Section", style="dim")
                    sample_table.add_column("Content Preview")
                    for s in mongo_stats["samples"]:
                        sample_table.add_row(s["section"], s["content"][:60] + "..." if len(s["content"]) > 60 else s["content"])
                    console.print(sample_table)
            else:
                console.print(Panel(
                    f"[red]❌ Disconnected[/red]\n{mongo_stats.get('error', '')}",
                    title="🍃 MongoDB",
                ))
            console.print()
        else:
            print("--- MongoDB ---")
            print(f"Status: {mongo_stats['status']}")
            if mongo_stats["status"] == "connected":
                print(f"Record Count: {mongo_stats['count']}")
            else:
                print(f"Error: {mongo_stats.get('error', '')}")
            print()
    
    # Neo4j
    if show_neo4j:
        neo4j_stats = get_neo4j_stats()
        if use_rich:
            if neo4j_stats["status"] == "connected":
                table = Table(title="🔗 Neo4j Knowledge Graph")
                table.add_column("Metric", style="cyan")
                table.add_column("Value", style="green")
                table.add_row("Status", "✅ Connected")
                table.add_row("Nodes", str(neo4j_stats["node_count"]))
                table.add_row("Relationships", str(neo4j_stats["relationship_count"]))
                console.print(table)
                
                if neo4j_stats.get("entity_types"):
                    type_table = Table(title="Entity Types")
                    type_table.add_column("Type", style="blue")
                    type_table.add_column("Count", style="green")
                    for t, c in neo4j_stats["entity_types"]:
                        type_table.add_row(str(t), str(c))
                    console.print(type_table)
            else:
                console.print(Panel(
                    f"[red]❌ Disconnected[/red]\n{neo4j_stats.get('error', '')}",
                    title="🔗 Neo4j",
                ))
        else:
            print("--- Neo4j ---")
            print(f"Status: {neo4j_stats['status']}")
            if neo4j_stats["status"] == "connected":
                print(f"Nodes: {neo4j_stats['node_count']}")
                print(f"Relationships: {neo4j_stats['relationship_count']}")
            else:
                print(f"Error: {neo4j_stats.get('error', '')}")


if __name__ == "__main__":
    main()

