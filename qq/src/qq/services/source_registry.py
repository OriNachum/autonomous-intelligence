"""Source Registry - collects and indexes sources during a conversation turn.

Each source (note, entity, file read, archive hit) gets a sequential [N] index.
The LLM sees these indices in its context and can reference them in its answer.
After the response, the registry formats a Sources footer to append.
"""

from typing import List, Dict, Any, Optional


class SourceRegistry:
    """Collects and indexes sources during a conversation turn."""

    def __init__(self):
        self._sources: List[Dict[str, Any]] = []

    def add(
        self,
        source_type: str,
        label: str,
        detail: str = "",
    ) -> int:
        """Register a source and return its [N] index.

        Args:
            source_type: Category — "note", "entity", "file", "core", "archive"
            label: Short identifier (filename, note excerpt, entity name)
            detail: Optional longer info (path, note_id, similarity score)

        Returns:
            The 1-based index assigned to this source.
        """
        index = len(self._sources) + 1
        self._sources.append({
            "index": index,
            "type": source_type,
            "label": label,
            "detail": detail,
        })
        return index

    def format_footer(self) -> str:
        """Format all registered sources as a markdown footer block.

        Returns:
            Formatted string starting with a separator, or empty string
            if no sources were registered.
        """
        if not self._sources:
            return ""
        lines = ["", "---", "**Sources:**"]
        for s in self._sources:
            detail = f" — {s['detail']}" if s["detail"] else ""
            lines.append(f"[{s['index']}] {s['label']}{detail}")
        return "\n".join(lines)

    def clear(self):
        """Reset the registry for the next turn."""
        self._sources.clear()

    @property
    def has_sources(self) -> bool:
        """Whether any sources have been registered this turn."""
        return len(self._sources) > 0

    @property
    def sources(self) -> List[Dict[str, Any]]:
        """Get a copy of all registered sources."""
        return list(self._sources)

    @property
    def count(self) -> int:
        """Number of registered sources."""
        return len(self._sources)
