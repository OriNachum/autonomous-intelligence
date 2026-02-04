"""Conversation history management with JSON persistence.

History is now session-isolated to support parallel QQ execution.
Each session gets its own history file under:
  ~/.qq/<agent>/sessions/<session_id>/history.json
"""

import json
import os
import tempfile
from pathlib import Path
from typing import Optional

from pydantic import BaseModel

from qq.session import get_session_dir


class HistoryEntry(BaseModel):
    """A single history entry."""
    role: str
    content: str
    timestamp: Optional[str] = None


class History:
    """
    Manages conversation history with sliding window and persistence.

    History is stored per-agent per-session in:
    ~/.qq/<agent>/sessions/<session_id>/history.json

    This enables parallel QQ execution without race conditions.
    """

    def __init__(
        self,
        agent_name: str = "default",
        history_dir: Optional[str] = None,
        window_size: int = 20,
    ):
        self.agent_name = agent_name
        self.window_size = window_size

        # Get base directory and session directory
        base_dir = Path(os.path.expanduser(history_dir or os.getenv("HISTORY_DIR", "~/.qq")))
        self.session_dir = get_session_dir(base_dir, agent_name)

        self.history_file = self.session_dir / "history.json"
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
        """Save history to disk atomically.

        Uses write-to-temp + atomic rename to prevent corruption
        if process is interrupted during write.
        """
        # Write to temp file first
        fd, tmp_path = tempfile.mkstemp(
            dir=self.session_dir,
            suffix=".json.tmp"
        )
        try:
            with os.fdopen(fd, 'w') as f:
                json.dump({"messages": self._messages}, f, indent=2)
            # Atomic rename (on POSIX, os.replace is atomic)
            os.replace(tmp_path, self.history_file)
        except Exception:
            # Clean up temp file on failure
            try:
                os.unlink(tmp_path)
            except OSError:
                pass
            raise

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
