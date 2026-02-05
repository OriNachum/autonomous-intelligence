"""Core Notes Manager - Protected, never-forgotten essential information.

Core notes contain crucial information that should persist indefinitely:
- User identity (name, location, role, preferences)
- Project identities (active projects being worked on)
- Key relationships (important people, collaborators)
- System configuration (hardware, setup)
"""

import fcntl
import os
import re
import tempfile
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import Optional, List, Dict, Any


# Protected categories that cannot be forgotten
PROTECTED_CATEGORIES = ["Identity", "Projects", "Relationships", "System"]

# Patterns that indicate core information
IDENTITY_PATTERNS = [
    r"\b(my name|i am|i'm|i prefer|call me)\b",
    r"\b(my role|i work|my job|i do)\b",
    r"\b(i live|my location|i'm from|i'm in)\b",
    r"\b(my email|my phone|contact me)\b",
]

PROJECT_PATTERNS = [
    r"\b(my project|i'm (building|working on|developing))\b",
    r"\b(our (project|system|app))\b",
]


class CoreNote:
    """Represents a single core note item."""

    def __init__(
        self,
        content: str,
        category: str,
        created_at: Optional[datetime] = None,
        source: Optional[str] = None,
    ):
        self.content = content
        self.category = category
        self.created_at = created_at or datetime.now()
        self.source = source  # Where it came from (conversation, migration, manual)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "content": self.content,
            "category": self.category,
            "created_at": self.created_at.isoformat(),
            "source": self.source,
        }


class CoreNotesManager:
    """
    Manages core.md file with protected, essential information.

    Core notes are never automatically forgotten. They can only be
    removed explicitly by the user or through manual intervention.
    """

    def __init__(self, memory_dir: Optional[str] = None):
        """
        Initialize the core notes manager.

        Args:
            memory_dir: Directory to store core.md (default: ./memory)
        """
        base_dir = memory_dir or os.getenv("MEMORY_DIR", "./memory")
        self.memory_dir = Path(base_dir).expanduser()
        self.memory_dir.mkdir(parents=True, exist_ok=True)
        self.core_file = self.memory_dir / "core.md"
        self.lock_file = self.memory_dir / "core.lock"
        self._content: Optional[str] = None

    @contextmanager
    def _file_lock(self, exclusive: bool = True):
        """Acquire file lock for core notes operations."""
        self.lock_file.touch(exist_ok=True)

        with open(self.lock_file, 'r') as f:
            try:
                fcntl.flock(f.fileno(),
                           fcntl.LOCK_EX if exclusive else fcntl.LOCK_SH)
                yield
            finally:
                fcntl.flock(f.fileno(), fcntl.LOCK_UN)

    def _create_template(self) -> str:
        """Create empty core notes template."""
        return f"""# Core Memory

Last updated: {datetime.now().strftime('%Y-%m-%d %H:%M')}

These are protected notes that will never be automatically forgotten.

## Identity
<!-- User's personal information: name, location, role, preferences -->

## Projects
<!-- Active projects the user is working on -->

## Relationships
<!-- Important people, collaborators, contacts -->

## System
<!-- Hardware, setup, configuration details -->

"""

    def load_notes(self) -> str:
        """Load existing core notes or return empty template."""
        with self._file_lock(exclusive=False):
            if self.core_file.exists():
                self._content = self.core_file.read_text()
            else:
                self._content = self._create_template()

        if not self.core_file.exists():
            self._save()

        return self._content

    def get_notes(self) -> str:
        """Get current core notes content."""
        if self._content is None:
            self.load_notes()
        return self._content or ""

    def _save(self) -> None:
        """Save core notes to file atomically with locking."""
        if self._content is None:
            return

        with self._file_lock(exclusive=True):
            # Update timestamp
            self._content = re.sub(
                r"Last updated: .*",
                f"Last updated: {datetime.now().strftime('%Y-%m-%d %H:%M')}",
                self._content
            )

            # Atomic write
            fd, tmp_path = tempfile.mkstemp(
                dir=self.memory_dir,
                suffix=".md.tmp"
            )
            try:
                with os.fdopen(fd, 'w') as f:
                    f.write(self._content)
                os.replace(tmp_path, self.core_file)
            except Exception:
                try:
                    os.unlink(tmp_path)
                except OSError:
                    pass
                raise

    def _save_unlocked(self) -> None:
        """Save without acquiring lock (caller must hold lock)."""
        if self._content is None:
            return

        self._content = re.sub(
            r"Last updated: .*",
            f"Last updated: {datetime.now().strftime('%Y-%m-%d %H:%M')}",
            self._content
        )

        fd, tmp_path = tempfile.mkstemp(
            dir=self.memory_dir,
            suffix=".md.tmp"
        )
        try:
            with os.fdopen(fd, 'w') as f:
                f.write(self._content)
            os.replace(tmp_path, self.core_file)
        except Exception:
            try:
                os.unlink(tmp_path)
            except OSError:
                pass
            raise

    def add_core(self, content: str, category: str, source: str = "auto") -> bool:
        """
        Add an item to core notes.

        Args:
            content: The note content
            category: Category (Identity, Projects, Relationships, System)
            source: Where this came from (auto, migration, manual)

        Returns:
            True if item was added, False if already exists or invalid category
        """
        if category not in PROTECTED_CATEGORIES:
            return False

        with self._file_lock(exclusive=True):
            # Reload to get latest content
            if self.core_file.exists():
                self._content = self.core_file.read_text()
            else:
                self._content = self._create_template()

            # Check if item already exists (case-insensitive partial match)
            content_lower = content.strip().lower()
            if content_lower in self._content.lower():
                return False

            # Find section and add item
            section_pattern = rf"(## {re.escape(category)}\n(?:<!--.*?-->\n)?)"
            match = re.search(section_pattern, self._content)

            if match:
                insert_pos = match.end()
                bullet_item = f"- {content.strip()}\n"
                self._content = (
                    self._content[:insert_pos] +
                    bullet_item +
                    self._content[insert_pos:]
                )
                self._save_unlocked()
                return True

        return False

    def remove_core(self, pattern: str, category: Optional[str] = None) -> bool:
        """
        Remove a core note item (requires explicit action).

        Args:
            pattern: Pattern to match for removal
            category: Optional category to limit search

        Returns:
            True if any items were removed
        """
        with self._file_lock(exclusive=True):
            if self.core_file.exists():
                self._content = self.core_file.read_text()
            else:
                return False

            original = self._content
            # Remove matching bullet items
            escaped_pattern = re.escape(pattern)
            item_pattern = rf"^- .*{escaped_pattern}.*\n"
            self._content = re.sub(item_pattern, "", self._content, flags=re.MULTILINE | re.IGNORECASE)

            if self._content != original:
                self._save_unlocked()
                return True

        return False

    def get_items_by_category(self, category: str) -> List[str]:
        """
        Get all items in a category.

        Args:
            category: Category name

        Returns:
            List of item strings
        """
        if self._content is None:
            self.load_notes()

        # Find section boundaries
        section_start = rf"## {re.escape(category)}\n"
        next_section = r"\n## "

        match = re.search(section_start, self._content)
        if not match:
            return []

        start_pos = match.end()

        # Find next section or end
        next_match = re.search(next_section, self._content[start_pos:])
        if next_match:
            end_pos = start_pos + next_match.start()
        else:
            end_pos = len(self._content)

        section_content = self._content[start_pos:end_pos]

        # Extract bullet items
        items = []
        for line in section_content.split('\n'):
            line = line.strip()
            if line.startswith('- '):
                items.append(line[2:])

        return items

    def get_all_items(self) -> Dict[str, List[str]]:
        """
        Get all core items organized by category.

        Returns:
            Dict mapping category to list of items
        """
        return {
            category: self.get_items_by_category(category)
            for category in PROTECTED_CATEGORIES
        }

    def is_protected(self, content: str) -> bool:
        """
        Check if content exists in core notes (protected).

        Args:
            content: Content to check

        Returns:
            True if content is in core notes
        """
        if self._content is None:
            self.load_notes()

        return content.strip().lower() in self._content.lower()

    @staticmethod
    def is_core_candidate(content: str) -> tuple[bool, str]:
        """
        Check if content looks like it should be a core note.

        Args:
            content: Content to analyze

        Returns:
            Tuple of (is_candidate, suggested_category)
        """
        content_lower = content.lower()

        # Check identity patterns
        for pattern in IDENTITY_PATTERNS:
            if re.search(pattern, content_lower):
                return (True, "Identity")

        # Check project patterns
        for pattern in PROJECT_PATTERNS:
            if re.search(pattern, content_lower):
                return (True, "Projects")

        # Check for relationship indicators
        if re.search(r"\b(collaborat|colleague|team|partner|friend)\b", content_lower):
            return (True, "Relationships")

        # Check for system/hardware indicators
        if re.search(r"\b(hardware|gpu|cpu|server|machine|setup|config)\b", content_lower):
            return (True, "System")

        return (False, "")

    def suggest_promotion(self, content: str, importance: float) -> Optional[str]:
        """
        Suggest whether a note should be promoted to core.

        Args:
            content: Note content
            importance: Current importance score

        Returns:
            Suggested category if should be promoted, None otherwise
        """
        # High importance notes are candidates
        if importance < 0.8:
            return None

        is_candidate, category = self.is_core_candidate(content)
        if is_candidate:
            return category

        return None
