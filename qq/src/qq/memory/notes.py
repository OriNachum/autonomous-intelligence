"""Notes file manager - handles notes.md persistence with incremental updates."""

import os
import re
from pathlib import Path
from typing import Optional, List
from datetime import datetime


class NotesManager:
    """
    Manages notes.md file with incremental updates.
    
    Notes are stored as a structured markdown file with sections.
    The manager supports adding, removing, and modifying items without
    recreating the entire file.
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
        self._content: Optional[str] = None
    
    def load_notes(self) -> str:
        """Load existing notes or return empty template."""
        if self.notes_file.exists():
            self._content = self.notes_file.read_text()
        else:
            self._content = self._create_template()
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

"""
    
    def get_notes(self) -> str:
        """Get current notes content."""
        if self._content is None:
            self.load_notes()
        return self._content or ""
    
    def _save(self) -> None:
        """Save notes to file."""
        if self._content is not None:
            # Update timestamp
            self._content = re.sub(
                r"Last updated: .*",
                f"Last updated: {datetime.now().strftime('%Y-%m-%d %H:%M')}",
                self._content
            )
            self.notes_file.write_text(self._content)
    
    def add_item(self, section: str, item: str) -> bool:
        """
        Add an item to a section if not already present.
        
        Args:
            section: Section name (e.g., "Key Topics")
            item: Item to add (without leading bullet)
            
        Returns:
            True if item was added, False if already exists
        """
        self.load_notes()
        
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
            self._save()
            return True
        
        return False
    
    def remove_item(self, section: str, item_pattern: str) -> bool:
        """
        Remove items matching pattern from a section.
        
        Args:
            section: Section name
            item_pattern: Regex pattern to match items to remove
            
        Returns:
            True if any items were removed
        """
        self.load_notes()
        
        original = self._content
        # Remove matching bullet items
        pattern = rf"^- .*{re.escape(item_pattern)}.*\n"
        self._content = re.sub(pattern, "", self._content, flags=re.MULTILINE)
        
        if self._content != original:
            self._save()
            return True
        
        return False
    
    def update_section(self, section: str, items: List[str]) -> None:
        """
        Replace all items in a section.
        
        Args:
            section: Section name
            items: New list of items
        """
        self.load_notes()
        
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
        self._save()
    
    def apply_diff(self, additions: List[dict], removals: List[str]) -> None:
        """
        Apply incremental changes to notes.
        
        Args:
            additions: List of {"section": str, "item": str} to add
            removals: List of item patterns to remove from any section
        """
        # Process removals first
        for pattern in removals:
            for section in ["Key Topics", "Important Facts", "People & Entities", "Ongoing Threads"]:
                self.remove_item(section, pattern)
        
        # Process additions
        for addition in additions:
            self.add_item(addition["section"], addition["item"])
