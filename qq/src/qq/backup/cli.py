"""qq-backup CLI - Command line interface for memory backups."""

import argparse
import sys
from pathlib import Path


def cmd_create(manager, verbose: bool = False) -> int:
    """Create a new backup."""
    print("Creating backup...")

    try:
        backup_path = manager.create_backup(trigger="manual")
        manifest = manager.get_backup(Path(backup_path).name)

        if manifest:
            print(f"\nBackup created: {backup_path}")
            print(manifest.summary())

            if manifest.is_complete:
                return 0
            else:
                print("\nWarning: Some stores failed to backup")
                return 1
        else:
            print(f"Backup created at {backup_path}")
            return 0

    except Exception as e:
        print(f"Error creating backup: {e}")
        return 1


def cmd_list(manager) -> int:
    """List all backups."""
    backups = manager.list_backups()

    if not backups:
        print("No backups found.")
        return 0

    print(f"Found {len(backups)} backup(s):\n")

    # Header
    print(f"{'ID':<20} {'Date':<20} {'Trigger':<8} {'Notes':<6} {'Mongo':<6} {'Neo4j':<12}")
    print("-" * 80)

    for backup in backups:
        date_str = backup.created_at.strftime("%Y-%m-%d %H:%M")
        notes_ok = "OK" if backup.notes_success else "FAIL"
        mongo_ok = "OK" if backup.mongodb_success else "FAIL"

        neo4j_str = "FAIL"
        if backup.neo4j_success:
            nodes = backup.neo4j_nodes or 0
            rels = backup.neo4j_rels or 0
            neo4j_str = f"{nodes}n/{rels}r"

        print(
            f"{backup.backup_id:<20} {date_str:<20} {backup.trigger:<8} "
            f"{notes_ok:<6} {mongo_ok:<6} {neo4j_str:<12}"
        )

    return 0


def cmd_status(manager) -> int:
    """Show backup status."""
    status = manager.status()

    print("Backup System Status")
    print("=" * 40)
    print(f"Backup directory: {status['backup_dir']}")
    print(f"Total backups: {status['total_backups']}")
    print(f"Retention: {status['retention_weeks']} weeks")
    print()

    if status["last_backup"]:
        print(f"Last backup: {status['last_backup']}")
        print(f"  Date: {status['last_backup_date']}")
    else:
        print("Last backup: None")

    if status["last_complete_backup"]:
        print(f"Last complete backup: {status['last_complete_backup']}")

    print()
    if status["needs_backup_today"]:
        print("Status: Daily backup NEEDED")
    else:
        print("Status: Daily backup already done")

    return 0


def cmd_restore(manager, backup_id: str, dry_run: bool, skip_embeddings: bool, notes_only: bool) -> int:
    """Restore from a backup."""
    from qq.backup.restore import restore_all

    backup_path = manager.get_backup_path(backup_id)
    if not backup_path:
        print(f"Backup not found: {backup_id}")
        return 1

    manifest = manager.get_backup(backup_id)
    if manifest:
        print(f"Restoring from backup: {backup_id}")
        print(manifest.summary())
        print()

    if dry_run:
        print("Dry run - no changes made")
        return 0

    # Create safety backup first
    print("Creating safety backup before restore...")
    try:
        safety_backup = manager.create_backup(trigger="pre-restore")
        print(f"Safety backup created: {safety_backup}")
    except Exception as e:
        print(f"Warning: Could not create safety backup: {e}")
        response = input("Continue anyway? [y/N] ")
        if response.lower() != "y":
            return 1

    # Initialize embeddings client if needed
    embeddings = None
    if not skip_embeddings and not notes_only:
        try:
            from qq.embeddings import EmbeddingClient
            embeddings = EmbeddingClient()
            if embeddings.is_available:
                print("Embeddings will be regenerated")
            else:
                print("Embeddings service not available - skipping regeneration")
                embeddings = None
        except Exception:
            print("Embeddings service not available - skipping regeneration")

    # Perform restore
    print("\nRestoring...")
    results = restore_all(
        backup_path,
        embeddings=embeddings,
        skip_embeddings=skip_embeddings,
        notes_only=notes_only,
    )

    # Print results
    print("\nRestore Results:")
    print("-" * 40)

    if "notes" in results:
        r = results["notes"]
        if r.get("success"):
            print(f"Notes: Restored ({r.get('size_bytes', 0):,} bytes)")
        else:
            print(f"Notes: FAILED - {r.get('error')}")

    if "mongodb" in results:
        r = results["mongodb"]
        if r.get("success"):
            print(f"MongoDB: Restored {r.get('restored', 0)} notes")
            if r.get("embedding_errors", 0) > 0:
                print(f"  (embedding errors: {r['embedding_errors']})")
        else:
            print(f"MongoDB: FAILED - {r.get('error')}")

    if "neo4j" in results:
        r = results["neo4j"]
        if r.get("success"):
            print(f"Neo4j: Restored {r.get('nodes', 0)} nodes, {r.get('relationships', 0)} relationships")
            if r.get("embedding_errors", 0) > 0:
                print(f"  (embedding errors: {r['embedding_errors']})")
        else:
            print(f"Neo4j: FAILED - {r.get('error')}")

    return 0 if results.get("success") else 1


def cmd_cleanup(manager, dry_run: bool) -> int:
    """Run retention cleanup."""
    if dry_run:
        print("Dry run - showing what would be deleted:")
    else:
        print("Running cleanup...")

    deleted = manager.cleanup_old_backups(dry_run=dry_run)

    if not deleted:
        print("No backups to clean up.")
        return 0

    action = "Would delete" if dry_run else "Deleted"
    print(f"\n{action} {len(deleted)} backup(s):")
    for backup_id in deleted:
        print(f"  - {backup_id}")

    return 0


def main():
    """Main entry point for qq-backup CLI."""
    parser = argparse.ArgumentParser(
        description="QQ Memory Backup - Backup and restore memory stores",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  qq-backup                   Create a new backup
  qq-backup --list            List all backups
  qq-backup --status          Show backup system status
  qq-backup --restore ID      Restore from backup ID
  qq-backup --cleanup         Run retention cleanup

Environment variables:
  QQ_BACKUP_DIR              Backup directory (default: ./backups)
  QQ_BACKUP_RETENTION_WEEKS  Weeks to retain (default: 4)
  QQ_BACKUP_ENABLED          Enable auto backups (default: true)
        """,
    )

    parser.add_argument("--list", "-l", action="store_true", help="List all backups")
    parser.add_argument("--status", "-s", action="store_true", help="Show backup status")
    parser.add_argument("--restore", "-r", metavar="ID", help="Restore from backup ID")
    parser.add_argument("--cleanup", "-c", action="store_true", help="Run retention cleanup")
    parser.add_argument("--dry-run", "-n", action="store_true", help="Preview without making changes")
    parser.add_argument("--skip-embeddings", action="store_true", help="Skip embedding regeneration on restore")
    parser.add_argument("--notes-only", action="store_true", help="Only restore notes.md")
    parser.add_argument("--verbose", "-v", action="store_true", help="Verbose output")

    args = parser.parse_args()

    # Load environment from .env if available
    try:
        from dotenv import load_dotenv
        load_dotenv()
    except ImportError:
        pass

    from qq.backup.manager import BackupManager
    manager = BackupManager()

    # Dispatch to appropriate command
    if args.list:
        return cmd_list(manager)
    elif args.status:
        return cmd_status(manager)
    elif args.restore:
        return cmd_restore(manager, args.restore, args.dry_run, args.skip_embeddings, args.notes_only)
    elif args.cleanup:
        return cmd_cleanup(manager, args.dry_run)
    else:
        # Default: create backup
        return cmd_create(manager, args.verbose)


if __name__ == "__main__":
    sys.exit(main())
