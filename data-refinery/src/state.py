"""Processing state management for resume support."""
import json
from pathlib import Path
from dataclasses import dataclass, field, asdict
from typing import Set


@dataclass
class ProcessingState:
    """Track processing progress for resume support."""
    
    processed_windows: Set[str] = field(default_factory=set)
    total_entities: int = 0
    total_relationships: int = 0
    
    def window_key(self, document_name: str, start_page: int) -> str:
        """Generate a unique key for a window."""
        return f"{document_name}:{start_page}"
    
    def is_processed(self, document_name: str, start_page: int) -> bool:
        """Check if a window has already been processed."""
        return self.window_key(document_name, start_page) in self.processed_windows
    
    def mark_processed(self, document_name: str, start_page: int, entities: int = 0, relationships: int = 0):
        """Mark a window as processed."""
        self.processed_windows.add(self.window_key(document_name, start_page))
        self.total_entities += entities
        self.total_relationships += relationships
    
    def save(self, filepath: Path):
        """Save state to a JSON file."""
        data = {
            "processed_windows": list(self.processed_windows),
            "total_entities": self.total_entities,
            "total_relationships": self.total_relationships,
        }
        with open(filepath, "w") as f:
            json.dump(data, f, indent=2)
    
    @classmethod
    def load(cls, filepath: Path) -> "ProcessingState":
        """Load state from a JSON file."""
        if not filepath.exists():
            return cls()
        
        with open(filepath, "r") as f:
            data = json.load(f)
        
        state = cls()
        state.processed_windows = set(data.get("processed_windows", []))
        state.total_entities = data.get("total_entities", 0)
        state.total_relationships = data.get("total_relationships", 0)
        return state
    
    def reset(self):
        """Reset all state."""
        self.processed_windows.clear()
        self.total_entities = 0
        self.total_relationships = 0
