"""Backup manager - unified backup orchestration for QQ memory stores."""

import os
import shutil
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import List, Optional

from qq.backup.manifest import BackupManifest, BackupInfo
from qq.backup.stores import backup_notes, backup_mongodb, backup_neo4j


class BackupManager:
    """
    Unified backup manager for all QQ memory stores.

    Handles:
    - Creating timestamped backup snapshots
    - Tracking last backup date for daily trigger
    - Cleanup based on retention policy
    - Listing and restoring backups
    """

    def __init__(self, backup_dir: Optional[str] = None):
        """
        Initialize backup manager.

        Args:
            backup_dir: Directory to store backups (default: QQ_BACKUP_DIR or ./backups)
        """
        self.backup_dir = Path(
            backup_dir or os.getenv("QQ_BACKUP_DIR", "./backups")
        ).expanduser()
        self.last_backup_file = self.backup_dir / ".last_backup"
        self.retention_weeks = int(os.getenv("QQ_BACKUP_RETENTION_WEEKS", "4"))

    def should_backup_today(self) -> bool:
        """
        Check if we need to create a daily backup.

        Returns True if:
        - No backup has ever been created, or
        - Last backup was on a different calendar day
        """
        # Check if backups are disabled
        if os.getenv("QQ_BACKUP_ENABLED", "true").lower() == "false":
            return False

        if not self.last_backup_file.exists():
            return True

        try:
            last_backup_date = self.last_backup_file.read_text().strip()
            today = datetime.now().strftime("%Y-%m-%d")
            return last_backup_date != today
        except Exception:
            return True

    def _mark_backup_done(self) -> None:
        """Update last backup marker with today's date."""
        self.backup_dir.mkdir(parents=True, exist_ok=True)
        self.last_backup_file.write_text(datetime.now().strftime("%Y-%m-%d"))

    def create_backup(self, trigger: str = "manual") -> str:
        """
        Create a full backup snapshot of all memory stores.

        Args:
            trigger: What triggered this backup ("daily", "manual", "scheduled")

        Returns:
            Path to the created backup directory
        """
        # Generate backup ID from timestamp
        backup_id = datetime.now().strftime("%Y-%m-%d_%H%M%S")
        backup_path = self.backup_dir / backup_id
        backup_path.mkdir(parents=True, exist_ok=True)

        # Create manifest
        manifest = BackupManifest(
            backup_id=backup_id,
            created_at=datetime.now(),
            trigger=trigger,
        )

        # Backup each store (continue on failure)
        manifest.notes = backup_notes(backup_path)
        manifest.mongodb = backup_mongodb(backup_path)
        manifest.neo4j = backup_neo4j(backup_path)

        # Save manifest
        manifest.save(backup_path)

        # Mark daily backup done
        if trigger == "daily":
            self._mark_backup_done()

        # Run cleanup after backup
        self.cleanup_old_backups()

        return str(backup_path)

    def list_backups(self) -> List[BackupInfo]:
        """
        List all available backups.

        Returns:
            List of BackupInfo objects sorted by date (newest first)
        """
        if not self.backup_dir.exists():
            return []

        backups = []
        for entry in self.backup_dir.iterdir():
            if not entry.is_dir():
                continue
            if entry.name.startswith("."):
                continue

            manifest_file = entry / "manifest.json"
            if not manifest_file.exists():
                continue

            try:
                manifest = BackupManifest.load(entry)
                backups.append(manifest.to_info())
            except Exception:
                # Skip corrupted backups
                continue

        # Sort by date, newest first
        backups.sort(key=lambda b: b.created_at, reverse=True)
        return backups

    def get_backup(self, backup_id: str) -> Optional[BackupManifest]:
        """
        Get full manifest for a specific backup.

        Args:
            backup_id: Backup identifier (timestamp string)

        Returns:
            BackupManifest or None if not found
        """
        backup_path = self.backup_dir / backup_id
        if not backup_path.exists():
            return None

        try:
            return BackupManifest.load(backup_path)
        except Exception:
            return None

    def cleanup_old_backups(self, dry_run: bool = False) -> List[str]:
        """
        Apply retention policy: keep one backup per week.

        - Keep all backups from current week
        - Keep oldest backup from each previous week
        - Delete rest

        Args:
            dry_run: If True, don't actually delete, just return what would be deleted

        Returns:
            List of deleted (or would-be-deleted) backup IDs
        """
        backups = self.list_backups()
        if not backups:
            return []

        # Group by ISO week (YYYY-WNN format)
        by_week: dict[str, List[BackupInfo]] = defaultdict(list)
        for backup in backups:
            week_key = backup.created_at.strftime("%Y-W%W")
            by_week[week_key].append(backup)

        current_week = datetime.now().strftime("%Y-W%W")
        to_delete: List[str] = []

        for week, week_backups in by_week.items():
            if week == current_week:
                # Keep all from current week
                continue

            # Sort by date (oldest first)
            week_backups.sort(key=lambda b: b.created_at)

            # Keep the oldest (first of the week), delete rest
            for backup in week_backups[1:]:
                to_delete.append(backup.backup_id)

        if not dry_run:
            for backup_id in to_delete:
                self._delete_backup(backup_id)

        return to_delete

    def _delete_backup(self, backup_id: str) -> bool:
        """
        Delete a backup directory.

        Args:
            backup_id: Backup identifier

        Returns:
            True if deleted successfully
        """
        backup_path = self.backup_dir / backup_id
        if not backup_path.exists():
            return False

        try:
            shutil.rmtree(backup_path)
            return True
        except Exception:
            return False

    def get_backup_path(self, backup_id: str) -> Optional[Path]:
        """
        Get the path to a backup directory.

        Args:
            backup_id: Backup identifier

        Returns:
            Path to backup directory or None if not found
        """
        backup_path = self.backup_dir / backup_id
        if backup_path.exists() and (backup_path / "manifest.json").exists():
            return backup_path
        return None

    def status(self) -> dict:
        """
        Get backup system status.

        Returns:
            Dict with status information
        """
        backups = self.list_backups()

        last_backup = None
        last_complete = None
        for backup in backups:
            if last_backup is None:
                last_backup = backup
            if backup.is_complete and last_complete is None:
                last_complete = backup
            if last_backup and last_complete:
                break

        return {
            "backup_dir": str(self.backup_dir),
            "total_backups": len(backups),
            "last_backup": last_backup.backup_id if last_backup else None,
            "last_backup_date": (
                last_backup.created_at.isoformat() if last_backup else None
            ),
            "last_complete_backup": (
                last_complete.backup_id if last_complete else None
            ),
            "needs_backup_today": self.should_backup_today(),
            "retention_weeks": self.retention_weeks,
        }
