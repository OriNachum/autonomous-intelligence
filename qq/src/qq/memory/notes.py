"""Notes file manager - handles notes.md persistence with incremental updates.

File locking and atomic saves are used to support parallel QQ execution.
Multiple instances can safely read/write to the same notes.md file.
"""

import fcntl
import os
import re
import tempfile
from contextlib import contextmanager
from pathlib import Path
from typing import Optional, List
from datetime import datetime


class NotesManager:
    """
    Manages notes.md file with incremental updates.

    Notes are stored as a structured markdown file with sections.
    The manager supports adding, removing, and modifying items without
    recreating the entire file.

    File locking (fcntl) is used to prevent race conditions when
    multiple QQ instances access the same notes file.
    """

    def __init__(self, memory_dir: Optional[str] = None):
        """
        Initialize the notes manager.

        Args:
            memory_dir: Directory to store notes.md (default: ./memory)
        """
        base_dir = memory_dir or os.getenv("MEMORY_DIR", "./memory")
        self.memory_dir = Path(base_dir).expanduser()
        self.memory_dir.mkdir(parents=True, exist_ok=True)
        self.notes_file = self.memory_dir / "notes.md"
        self.lock_file = self.memory_dir / "notes.lock"
        self._content: Optional[str] = None

    @contextmanager
    def _file_lock(self, exclusive: bool = True):
        """Acquire file lock for notes operations.

        Args:
            exclusive: If True, acquire exclusive (write) lock.
                       If False, acquire shared (read) lock.

        Yields when lock is acquired, releases on exit.
        """
        # Ensure lock file exists
        self.lock_file.touch(exist_ok=True)

        with open(self.lock_file, 'r') as f:
            try:
                fcntl.flock(f.fileno(),
                           fcntl.LOCK_EX if exclusive else fcntl.LOCK_SH)
                yield
            finally:
                fcntl.flock(f.fileno(), fcntl.LOCK_UN)

    def load_notes(self) -> str:
        """Load existing notes or return empty template.

        Uses shared (read) lock to allow concurrent reads.
        """
        with self._file_lock(exclusive=False):
            if self.notes_file.exists():
                self._content = self.notes_file.read_text()
            else:
                self._content = self._create_template()
                # Need to save, upgrade to exclusive lock

        # If we created a new template, save it
        if not self.notes_file.exists():
            self._save()

        return self._content

    def _create_template(self) -> str:
        """Create empty notes template."""
        return f"""# QQ Memory Notes

Last updated: {datetime.now().strftime('%Y-%m-%d %H:%M')}

## Key Topics

## Important Facts

## People & Entities

## Ongoing Threads

## File Knowledge

"""

    def get_notes(self) -> str:
        """Get current notes content."""
        if self._content is None:
            self.load_notes()
        return self._content or ""

    def _save(self) -> None:
        """Save notes to file atomically with locking.

        Uses exclusive lock + atomic write (temp file + rename)
        to prevent corruption from parallel writes.
        """
        if self._content is None:
            return

        with self._file_lock(exclusive=True):
            # Update timestamp
            self._content = re.sub(
                r"Last updated: .*",
                f"Last updated: {datetime.now().strftime('%Y-%m-%d %H:%M')}",
                self._content
            )

            # Atomic write: temp file + rename
            fd, tmp_path = tempfile.mkstemp(
                dir=self.memory_dir,
                suffix=".md.tmp"
            )
            try:
                with os.fdopen(fd, 'w') as f:
                    f.write(self._content)
                # Atomic rename
                os.replace(tmp_path, self.notes_file)
            except Exception:
                # Clean up temp file on failure
                try:
                    os.unlink(tmp_path)
                except OSError:
                    pass
                raise

    def add_item(self, section: str, item: str) -> bool:
        """
        Add an item to a section if not already present.

        Args:
            section: Section name (e.g., "Key Topics")
            item: Item to add (without leading bullet)

        Returns:
            True if item was added, False if already exists
        """
        with self._file_lock(exclusive=True):
            # Reload to get latest content
            if self.notes_file.exists():
                self._content = self.notes_file.read_text()
            else:
                self._content = self._create_template()

            # Check if item already exists
            if item.strip() in self._content:
                return False

            # Find section and add item
            section_pattern = rf"(## {re.escape(section)}\n)"
            match = re.search(section_pattern, self._content)

            if match:
                insert_pos = match.end()
                bullet_item = f"- {item.strip()}\n"
                self._content = (
                    self._content[:insert_pos] +
                    bullet_item +
                    self._content[insert_pos:]
                )
                self._save_unlocked()
                return True

            return False

    def _save_unlocked(self) -> None:
        """Save without acquiring lock (caller must hold lock)."""
        if self._content is None:
            return

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
            os.replace(tmp_path, self.notes_file)
        except Exception:
            try:
                os.unlink(tmp_path)
            except OSError:
                pass
            raise

    def remove_item(self, section: str, item_pattern: str) -> bool:
        """
        Remove items matching pattern from a section.

        Args:
            section: Section name
            item_pattern: Regex pattern to match items to remove

        Returns:
            True if any items were removed
        """
        with self._file_lock(exclusive=True):
            # Reload to get latest content
            if self.notes_file.exists():
                self._content = self.notes_file.read_text()
            else:
                return False

            original = self._content
            # Remove matching bullet items
            pattern = rf"^- .*{re.escape(item_pattern)}.*\n"
            self._content = re.sub(pattern, "", self._content, flags=re.MULTILINE)

            if self._content != original:
                self._save_unlocked()
                return True

            return False

    def update_section(self, section: str, items: List[str]) -> None:
        """
        Replace all items in a section.

        Args:
            section: Section name
            items: New list of items
        """
        with self._file_lock(exclusive=True):
            # Reload to get latest content
            if self.notes_file.exists():
                self._content = self.notes_file.read_text()
            else:
                self._content = self._create_template()

            # Find section boundaries
            section_start = rf"## {re.escape(section)}\n"
            next_section = r"\n## "

            match = re.search(section_start, self._content)
            if not match:
                return

            start_pos = match.end()

            # Find next section or end
            next_match = re.search(next_section, self._content[start_pos:])
            if next_match:
                end_pos = start_pos + next_match.start()
            else:
                end_pos = len(self._content)

            # Build new section content
            new_items = "\n".join(f"- {item.strip()}" for item in items if item.strip())
            if new_items:
                new_items += "\n"

            self._content = (
                self._content[:start_pos] +
                new_items +
                self._content[end_pos:]
            )
            self._save_unlocked()

    def apply_diff(self, additions: List[dict], removals: List[str]) -> None:
        """
        Apply incremental changes to notes.

        Args:
            additions: List of {"section": str, "item": str} to add
            removals: List of item patterns to remove from any section
        """
        # Process removals first
        for pattern in removals:
            for section in ["Key Topics", "Important Facts", "People & Entities", "Ongoing Threads", "File Knowledge"]:
                self.remove_item(section, pattern)

        # Process additions
        for addition in additions:
            self.add_item(addition["section"], addition["item"])

    def get_all_items(self) -> List[dict]:
        """
        Get all items from all sections.

        Returns:
            List of {"section": str, "item": str}
        """
        if self._content is None:
            self.load_notes()

        items = []
        sections = ["Key Topics", "Important Facts", "People & Entities", "Ongoing Threads", "File Knowledge"]

        for section in sections:
            section_items = self.get_section_items(section)
            for item in section_items:
                items.append({"section": section, "item": item})

        return items

    def get_section_items(self, section: str) -> List[str]:
        """
        Get all items from a specific section.

        Args:
            section: Section name

        Returns:
            List of item strings
        """
        if self._content is None:
            self.load_notes()

        # Find section boundaries
        section_start = rf"## {re.escape(section)}\n"
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

    def remove_exact_item(self, item: str) -> bool:
        """
        Remove an item by exact content match.

        Args:
            item: Exact item text to remove

        Returns:
            True if item was removed
        """
        with self._file_lock(exclusive=True):
            if self.notes_file.exists():
                self._content = self.notes_file.read_text()
            else:
                return False

            original = self._content
            # Escape special regex chars and remove the exact line
            escaped = re.escape(item.strip())
            pattern = rf"^- {escaped}\n"
            self._content = re.sub(pattern, "", self._content, flags=re.MULTILINE)

            if self._content != original:
                self._save_unlocked()
                return True

            return False

    def count_items(self) -> int:
        """Count total number of items across all sections."""
        return len(self.get_all_items())

    def rebuild_with_items(self, items: List[dict]) -> None:
        """
        Rebuild notes.md with a specific set of items.

        Args:
            items: List of {"section": str, "item": str}
        """
        with self._file_lock(exclusive=True):
            # Start with fresh template
            self._content = self._create_template()

            # Group items by section
            by_section = {}
            for item in items:
                section = item.get("section", "Key Topics")
                if section not in by_section:
                    by_section[section] = []
                by_section[section].append(item["item"])

            # Update each section
            for section, section_items in by_section.items():
                # Find section and add items
                section_pattern = rf"(## {re.escape(section)}\n)"
                match = re.search(section_pattern, self._content)

                if match:
                    insert_pos = match.end()
                    items_text = "\n".join(f"- {item.strip()}" for item in section_items if item.strip())
                    if items_text:
                        items_text += "\n"
                    self._content = (
                        self._content[:insert_pos] +
                        items_text +
                        self._content[insert_pos:]
                    )

            self._save_unlocked()
