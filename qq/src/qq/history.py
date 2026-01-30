"""Conversation history management with JSON persistence."""

import json
import os
from pathlib import Path
from typing import Optional

from pydantic import BaseModel


class HistoryEntry(BaseModel):
    """A single history entry."""
    role: str
    content: str
    timestamp: Optional[str] = None


class History:
    """
    Manages conversation history with sliding window and persistence.
    
    History is stored per-agent in ~/.qq/<agent>/history.json
    """
    
    def __init__(
        self,
        agent_name: str = "default",
        history_dir: Optional[str] = None,
        window_size: int = 20,
    ):
        self.agent_name = agent_name
        self.window_size = window_size
        
        # Expand ~ and set up directory
        base_dir = history_dir or os.getenv("HISTORY_DIR", "~/.qq")
        self.history_dir = Path(os.path.expanduser(base_dir)) / agent_name
        self.history_dir.mkdir(parents=True, exist_ok=True)
        
        self.history_file = self.history_dir / "history.json"
        self._messages: list[dict] = []
        
        # Load existing history
        self._load()
    
    def _load(self) -> None:
        """Load history from disk."""
        if self.history_file.exists():
            try:
                with open(self.history_file, "r") as f:
                    data = json.load(f)
                    self._messages = data.get("messages", [])
            except (json.JSONDecodeError, IOError):
                self._messages = []
    
    def _save(self) -> None:
        """Save history to disk."""
        with open(self.history_file, "w") as f:
            json.dump({"messages": self._messages}, f, indent=2)
    
    def add(self, role: str, content: str) -> None:
        """Add a message to history and save."""
        from datetime import datetime
        
        self._messages.append({
            "role": role,
            "content": content,
            "timestamp": datetime.now().isoformat(),
        })
        self._save()
    
    def get_messages(self, include_timestamps: bool = False) -> list[dict]:
        """
        Get the last N messages as a sliding window.
        
        Returns messages in OpenAI format (role, content only).
        """
        # Get last window_size messages
        recent = self._messages[-self.window_size:]
        
        if include_timestamps:
            return recent
        
        # Return only role and content for API calls
        return [{"role": m["role"], "content": m["content"]} for m in recent]
    
    def clear(self) -> None:
        """Clear all history."""
        self._messages = []
        self._save()
    
    def get_full_history(self) -> list[dict]:
        """Get all messages (not windowed)."""
        return self._messages.copy()
    
    @property
    def count(self) -> int:
        """Number of messages in history."""
        return len(self._messages)
    
    @property
    def windowed_count(self) -> int:
        """Number of messages in current window."""
        return min(len(self._messages), self.window_size)
