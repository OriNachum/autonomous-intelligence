"""Archive Manager - Stores forgotten notes with restore capability.

Archived notes are not included in context retrieval but can be
searched and restored on demand.
"""

import json
import logging
import os
from datetime import datetime, timedelta
from pathlib import Path
from typing import List, Dict, Any, Optional

logger = logging.getLogger("qq.archive")

# Configuration
ARCHIVE_RETENTION_DAYS = int(os.getenv("QQ_ARCHIVE_RETENTION_DAYS", "90"))


class ArchivedNote:
    """Represents an archived note."""

    def __init__(
        self,
        note_id: str,
        content: str,
        section: str,
        importance: float,
        reason: str,
        archived_at: datetime,
        original_created_at: Optional[datetime] = None,
        access_count: int = 0,
        metadata: Optional[Dict[str, Any]] = None,
    ):
        self.note_id = note_id
        self.content = content
        self.section = section
        self.importance = importance
        self.reason = reason
        self.archived_at = archived_at
        self.original_created_at = original_created_at
        self.access_count = access_count
        self.metadata = metadata or {}

    def to_dict(self) -> Dict[str, Any]:
        return {
            "note_id": self.note_id,
            "content": self.content,
            "section": self.section,
            "importance": self.importance,
            "reason": self.reason,
            "archived_at": self.archived_at.isoformat(),
            "original_created_at": self.original_created_at.isoformat() if self.original_created_at else None,
            "access_count": self.access_count,
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ArchivedNote":
        return cls(
            note_id=data["note_id"],
            content=data["content"],
            section=data.get("section", ""),
            importance=data.get("importance", 0.0),
            reason=data.get("reason", "unknown"),
            archived_at=datetime.fromisoformat(data["archived_at"]),
            original_created_at=datetime.fromisoformat(data["original_created_at"]) if data.get("original_created_at") else None,
            access_count=data.get("access_count", 0),
            metadata=data.get("metadata", {}),
        )


class ArchiveManager:
    """
    Manages archived notes in a JSONL file.

    Notes that fall below the importance threshold are archived here
    rather than deleted. They can be searched and restored on demand.
    """

    def __init__(
        self,
        memory_dir: Optional[str] = None,
        mongo_store: Optional[Any] = None,
        retention_days: int = ARCHIVE_RETENTION_DAYS,
    ):
        """
        Initialize the archive manager.

        Args:
            memory_dir: Directory for archive file (default: ./memory)
            mongo_store: MongoNotesStore instance for note operations
            retention_days: Days to retain archived notes before purging
        """
        base_dir = memory_dir or os.getenv("MEMORY_DIR", "./memory")
        self.memory_dir = Path(base_dir).expanduser()
        self.memory_dir.mkdir(parents=True, exist_ok=True)
        self.archive_file = self.memory_dir / "archive.jsonl"
        self.mongo_store = mongo_store
        self.retention_days = retention_days
        self._initialized = False

    def _ensure_initialized(self) -> None:
        """Lazy initialize MongoDB store."""
        if self._initialized:
            return

        if self.mongo_store is None:
            try:
                from qq.memory.mongo_store import MongoNotesStore
                self.mongo_store = MongoNotesStore()
            except Exception as e:
                logger.warning(f"Could not initialize MongoDB: {e}")

        self._initialized = True

    def archive_note(
        self,
        note_id: str,
        reason: str = "low_importance",
        remove_from_mongo: bool = True,
    ) -> bool:
        """
        Archive a note by ID.

        Args:
            note_id: ID of the note to archive
            reason: Reason for archiving
            remove_from_mongo: Whether to remove from MongoDB

        Returns:
            True if note was archived
        """
        self._ensure_initialized()

        if not self.mongo_store:
            logger.warning("MongoDB not available for archiving")
            return False

        # Get the note from MongoDB
        note = self.mongo_store.get_note(note_id)
        if not note:
            logger.warning(f"Note {note_id} not found for archiving")
            return False

        # Create archived note
        archived = ArchivedNote(
            note_id=note_id,
            content=note.get("content", ""),
            section=note.get("section", ""),
            importance=note.get("importance", 0.0),
            reason=reason,
            archived_at=datetime.now(),
            original_created_at=note.get("created_at"),
            access_count=note.get("access_count", 0),
            metadata=note.get("metadata", {}),
        )

        # Append to archive file
        try:
            with open(self.archive_file, 'a') as f:
                f.write(json.dumps(archived.to_dict()) + '\n')
        except Exception as e:
            logger.error(f"Failed to write to archive: {e}")
            return False

        # Remove from MongoDB
        if remove_from_mongo:
            self.mongo_store.delete_note(note_id)

        logger.info(f"Archived note {note_id}: {reason}")
        return True

    def archive_by_content(
        self,
        content: str,
        reason: str = "low_importance",
    ) -> bool:
        """
        Archive a note by its content.

        Args:
            content: Content of the note to archive
            reason: Reason for archiving

        Returns:
            True if note was archived
        """
        self._ensure_initialized()

        if not self.mongo_store:
            return False

        # Find note by content
        note = self.mongo_store.collection.find_one({"content": content})
        if not note:
            logger.warning(f"Note with content not found for archiving")
            return False

        return self.archive_note(note.get("note_id"), reason)

    def restore_note(
        self,
        note_id: str,
        boost_importance: float = 0.1,
    ) -> bool:
        """
        Restore an archived note back to active memory.

        Args:
            note_id: ID of the note to restore
            boost_importance: Amount to boost importance on restore

        Returns:
            True if note was restored
        """
        self._ensure_initialized()

        # Find in archive
        archived = self._find_in_archive(note_id)
        if not archived:
            logger.warning(f"Note {note_id} not found in archive")
            return False

        if not self.mongo_store:
            logger.warning("MongoDB not available for restore")
            return False

        # Restore to MongoDB with boosted importance
        try:
            # Generate new embedding if possible
            embedding = []
            try:
                from qq.embeddings import EmbeddingClient
                client = EmbeddingClient()
                embedding = client.get_embedding(archived.content)
            except Exception:
                pass

            new_importance = min(1.0, archived.importance + boost_importance)

            self.mongo_store.upsert_note(
                note_id=archived.note_id,
                content=archived.content,
                embedding=embedding,
                section=archived.section,
                metadata={
                    "restored_from_archive": True,
                    "restored_at": datetime.now().isoformat(),
                    **archived.metadata,
                },
            )

            # Update importance and other fields
            self.mongo_store.collection.update_one(
                {"note_id": archived.note_id},
                {"$set": {
                    "importance": new_importance,
                    "access_count": archived.access_count,
                    "created_at": archived.original_created_at or datetime.now(),
                }}
            )

            # Mark as restored in archive (don't delete, keep for history)
            self._mark_restored_in_archive(note_id)

            logger.info(f"Restored note {note_id} with importance {new_importance}")
            return True

        except Exception as e:
            logger.error(f"Failed to restore note: {e}")
            return False

    def _find_in_archive(self, note_id: str) -> Optional[ArchivedNote]:
        """Find a note in the archive by ID."""
        if not self.archive_file.exists():
            return None

        with open(self.archive_file, 'r') as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    data = json.loads(line)
                    if data.get("note_id") == note_id and not data.get("restored"):
                        return ArchivedNote.from_dict(data)
                except json.JSONDecodeError:
                    continue

        return None

    def _mark_restored_in_archive(self, note_id: str) -> None:
        """Mark a note as restored in the archive file."""
        if not self.archive_file.exists():
            return

        # Read all lines
        with open(self.archive_file, 'r') as f:
            lines = f.readlines()

        # Update the matching line
        updated_lines = []
        for line in lines:
            line = line.strip()
            if not line:
                continue
            try:
                data = json.loads(line)
                if data.get("note_id") == note_id:
                    data["restored"] = True
                    data["restored_at"] = datetime.now().isoformat()
                updated_lines.append(json.dumps(data) + '\n')
            except json.JSONDecodeError:
                updated_lines.append(line + '\n')

        # Write back
        with open(self.archive_file, 'w') as f:
            f.writelines(updated_lines)

    def search_archive(
        self,
        query: str,
        limit: int = 10,
        include_restored: bool = False,
    ) -> List[ArchivedNote]:
        """
        Search the archive for notes matching a query.

        Args:
            query: Search query (substring match)
            limit: Maximum results
            include_restored: Whether to include already-restored notes

        Returns:
            List of matching archived notes
        """
        if not self.archive_file.exists():
            return []

        results = []
        query_lower = query.lower()

        with open(self.archive_file, 'r') as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    data = json.loads(line)

                    # Skip restored unless requested
                    if data.get("restored") and not include_restored:
                        continue

                    # Check for query match
                    content = data.get("content", "").lower()
                    if query_lower in content:
                        results.append(ArchivedNote.from_dict(data))

                        if len(results) >= limit:
                            break
                except json.JSONDecodeError:
                    continue

        return results

    def get_archive_stats(self) -> Dict[str, Any]:
        """
        Get statistics about the archive.

        Returns:
            Dict with archive statistics
        """
        if not self.archive_file.exists():
            return {
                "total": 0,
                "active": 0,
                "restored": 0,
                "by_section": {},
                "by_reason": {},
            }

        total = 0
        active = 0
        restored = 0
        by_section: Dict[str, int] = {}
        by_reason: Dict[str, int] = {}

        with open(self.archive_file, 'r') as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    data = json.loads(line)
                    total += 1

                    if data.get("restored"):
                        restored += 1
                    else:
                        active += 1

                    section = data.get("section", "unknown")
                    by_section[section] = by_section.get(section, 0) + 1

                    reason = data.get("reason", "unknown")
                    by_reason[reason] = by_reason.get(reason, 0) + 1

                except json.JSONDecodeError:
                    continue

        return {
            "total": total,
            "active": active,
            "restored": restored,
            "by_section": by_section,
            "by_reason": by_reason,
        }

    def purge_old_archives(
        self,
        days: Optional[int] = None,
    ) -> int:
        """
        Remove archived notes older than retention period.

        Args:
            days: Days to retain (default: retention_days)

        Returns:
            Number of notes purged
        """
        days = days or self.retention_days
        cutoff = datetime.now() - timedelta(days=days)
        purged = 0

        if not self.archive_file.exists():
            return 0

        # Read all lines
        with open(self.archive_file, 'r') as f:
            lines = f.readlines()

        # Filter out old entries
        kept_lines = []
        for line in lines:
            line = line.strip()
            if not line:
                continue
            try:
                data = json.loads(line)
                archived_at = datetime.fromisoformat(data.get("archived_at", ""))

                if archived_at >= cutoff:
                    kept_lines.append(json.dumps(data) + '\n')
                else:
                    purged += 1
            except (json.JSONDecodeError, ValueError):
                # Keep malformed lines to avoid data loss
                kept_lines.append(line + '\n')

        # Write back
        with open(self.archive_file, 'w') as f:
            f.writelines(kept_lines)

        logger.info(f"Purged {purged} archived notes older than {days} days")
        return purged

    def archive_low_importance(
        self,
        threshold: float = 0.05,
    ) -> int:
        """
        Archive all notes below importance threshold.

        Args:
            threshold: Importance threshold

        Returns:
            Number of notes archived
        """
        self._ensure_initialized()

        if not self.mongo_store:
            return 0

        from qq.memory.importance import ImportanceScorer, ScoredNote
        scorer = ImportanceScorer()

        # Find notes with low importance after decay
        notes = list(self.mongo_store.collection.find({}))
        archived = 0

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

            if decayed < threshold:
                if self.archive_note(scored.note_id, reason=f"importance_decay_{decayed:.3f}"):
                    archived += 1

        logger.info(f"Archived {archived} notes below threshold {threshold}")
        return archived
