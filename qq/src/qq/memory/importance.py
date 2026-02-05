"""Importance Scoring System - Assigns and manages note importance for decay/forgetting.

Notes are scored based on:
- Identity markers (name, location, role, preferences)
- Project references
- Specificity (concrete facts vs. vague observations)
- Recurrence (mentioned multiple times)
- Access frequency (how often retrieved)
"""

import os
import re
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional, Tuple


# Environment configuration
CORE_THRESHOLD = float(os.getenv("QQ_CORE_THRESHOLD", "0.8"))
ARCHIVE_THRESHOLD = float(os.getenv("QQ_ARCHIVE_THRESHOLD", "0.05"))
MIN_RETRIEVAL_IMPORTANCE = float(os.getenv("QQ_MIN_RETRIEVAL_IMPORTANCE", "0.2"))
BASE_DECAY_RATE = float(os.getenv("QQ_BASE_DECAY_RATE", "0.01"))


# Importance classification levels
IMPORTANCE_LEVELS = {
    "core": 1.0,     # User identity, preferences, projects
    "high": 0.7,     # Specific decisions, important facts
    "medium": 0.4,   # Research topics, ongoing investigations
    "low": 0.2,      # Temporary observations, single-mention facts
}

# Patterns that indicate high importance
IDENTITY_PATTERNS = [
    (r"\b(my name|i am|i'm|i prefer|call me)\b", 0.5),
    (r"\b(my role|i work|my job|profession)\b", 0.4),
    (r"\b(i live|my location|i'm from|i'm in)\b", 0.4),
    (r"\b(my email|my phone|contact)\b", 0.3),
]

PROJECT_PATTERNS = [
    (r"\b(my project|building|working on|developing)\b", 0.3),
    (r"\b(our (project|system|app|codebase))\b", 0.3),
]

SPECIFICITY_PATTERNS = [
    # Specific facts are more important
    (r"\b\d{4}[-/]\d{2}[-/]\d{2}\b", 0.1),  # Dates
    (r"\b\d+(\.\d+)?\s*(GB|MB|KB|TB)\b", 0.1),  # Sizes
    (r"\b(version|v)\s*\d+\.\d+", 0.1),  # Versions
    (r"https?://", 0.05),  # URLs
]

# Section weights - some sections are inherently more important
SECTION_WEIGHTS = {
    "People & Entities": 0.2,
    "Identity": 0.3,
    "Projects": 0.2,
    "Important Facts": 0.1,
    "Key Topics": 0.0,
    "Ongoing Threads": 0.0,
    "File Knowledge": -0.1,
}


@dataclass
class ScoredNote:
    """A note with importance metadata."""
    content: str
    section: str
    importance: float = 0.5
    access_count: int = 0
    last_accessed: Optional[datetime] = None
    created_at: datetime = field(default_factory=datetime.now)
    decay_rate: float = BASE_DECAY_RATE
    note_id: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "content": self.content,
            "section": self.section,
            "importance": self.importance,
            "access_count": self.access_count,
            "last_accessed": self.last_accessed.isoformat() if self.last_accessed else None,
            "created_at": self.created_at.isoformat(),
            "decay_rate": self.decay_rate,
            "note_id": self.note_id,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ScoredNote":
        return cls(
            content=data["content"],
            section=data.get("section", ""),
            importance=data.get("importance", 0.5),
            access_count=data.get("access_count", 0),
            last_accessed=datetime.fromisoformat(data["last_accessed"]) if data.get("last_accessed") else None,
            created_at=datetime.fromisoformat(data["created_at"]) if data.get("created_at") else datetime.now(),
            decay_rate=data.get("decay_rate", BASE_DECAY_RATE),
            note_id=data.get("note_id"),
        )


class ImportanceScorer:
    """
    Scores notes based on content analysis and usage patterns.

    Initial scoring is based on content patterns (identity markers, specificity).
    Over time, importance decays unless the note is accessed frequently.
    """

    def __init__(
        self,
        core_threshold: float = CORE_THRESHOLD,
        archive_threshold: float = ARCHIVE_THRESHOLD,
        base_decay_rate: float = BASE_DECAY_RATE,
    ):
        self.core_threshold = core_threshold
        self.archive_threshold = archive_threshold
        self.base_decay_rate = base_decay_rate

    def score_note(
        self,
        content: str,
        section: str = "",
        importance_hint: Optional[str] = None,
    ) -> float:
        """
        Calculate initial importance score for a note.

        Args:
            content: The note text
            section: Section the note belongs to
            importance_hint: Optional hint from extraction (core, high, medium, low)

        Returns:
            Float importance score between 0.0 and 1.0
        """
        # Start with base score
        if importance_hint and importance_hint in IMPORTANCE_LEVELS:
            score = IMPORTANCE_LEVELS[importance_hint]
        else:
            score = 0.3  # Default baseline

        content_lower = content.lower()

        # Add identity pattern bonuses
        for pattern, bonus in IDENTITY_PATTERNS:
            if re.search(pattern, content_lower):
                score += bonus

        # Add project pattern bonuses
        for pattern, bonus in PROJECT_PATTERNS:
            if re.search(pattern, content_lower):
                score += bonus

        # Add specificity bonuses
        for pattern, bonus in SPECIFICITY_PATTERNS:
            if re.search(pattern, content_lower):
                score += bonus

        # Add section weight
        if section in SECTION_WEIGHTS:
            score += SECTION_WEIGHTS[section]

        # Length penalty - very short notes are less valuable
        if len(content) < 20:
            score -= 0.1
        # Very long notes may be less specific
        elif len(content) > 500:
            score -= 0.05

        # Clamp to valid range
        return max(0.0, min(1.0, score))

    def classify_importance(self, content: str, section: str = "") -> str:
        """
        Classify a note into importance level.

        Args:
            content: The note text
            section: Section the note belongs to

        Returns:
            Importance level string (core, high, medium, low)
        """
        score = self.score_note(content, section)

        if score >= 0.8:
            return "core"
        elif score >= 0.5:
            return "high"
        elif score >= 0.3:
            return "medium"
        else:
            return "low"

    def decay_importance(
        self,
        note: ScoredNote,
        current_time: Optional[datetime] = None,
    ) -> float:
        """
        Calculate decayed importance for a note.

        Args:
            note: The scored note
            current_time: Current time (defaults to now)

        Returns:
            Decayed importance score
        """
        if current_time is None:
            current_time = datetime.now()

        # Calculate days since creation
        days_since_creation = (current_time - note.created_at).days

        # Calculate days since last access
        if note.last_accessed:
            days_since_access = (current_time - note.last_accessed).days
        else:
            days_since_access = days_since_creation

        # Base decay rate (configurable per note)
        decay_rate = note.decay_rate or self.base_decay_rate

        # Access frequency bonus (0-0.5)
        # More accesses = more important
        access_bonus = min(0.5, note.access_count * 0.05)

        # Age factor (older notes become less relevant unless accessed)
        # Gentle decay: 1.0 at day 0, ~0.5 at day 100
        age_factor = 1.0 / (1 + days_since_creation * 0.01)

        # Staleness penalty (not accessed recently)
        staleness = days_since_access * decay_rate

        # Calculate decayed importance
        decayed = note.importance - staleness
        adjusted = (decayed + access_bonus) * age_factor

        return max(0.0, min(1.0, adjusted))

    def decay_notes(
        self,
        notes: List[ScoredNote],
        current_time: Optional[datetime] = None,
    ) -> List[Tuple[ScoredNote, float]]:
        """
        Apply decay to a list of notes.

        Args:
            notes: List of scored notes
            current_time: Current time (defaults to now)

        Returns:
            List of (note, decayed_importance) tuples
        """
        return [
            (note, self.decay_importance(note, current_time))
            for note in notes
        ]

    def get_archival_candidates(
        self,
        notes: List[ScoredNote],
        threshold: Optional[float] = None,
        current_time: Optional[datetime] = None,
    ) -> List[ScoredNote]:
        """
        Get notes that should be archived (importance below threshold).

        Args:
            notes: List of scored notes
            threshold: Importance threshold (default: archive_threshold)
            current_time: Current time for decay calculation

        Returns:
            List of notes to archive
        """
        threshold = threshold or self.archive_threshold
        candidates = []

        for note in notes:
            decayed = self.decay_importance(note, current_time)
            if decayed < threshold:
                candidates.append(note)

        return candidates

    def get_promotion_candidates(
        self,
        notes: List[ScoredNote],
        threshold: Optional[float] = None,
    ) -> List[ScoredNote]:
        """
        Get notes that could be promoted to core.

        Args:
            notes: List of scored notes
            threshold: Importance threshold (default: core_threshold)

        Returns:
            List of notes to potentially promote
        """
        threshold = threshold or self.core_threshold
        candidates = []

        for note in notes:
            # Only consider notes with high importance AND frequent access
            if note.importance >= threshold and note.access_count >= 3:
                candidates.append(note)

        return candidates

    def should_retrieve(
        self,
        note: ScoredNote,
        threshold: Optional[float] = None,
        current_time: Optional[datetime] = None,
    ) -> bool:
        """
        Check if a note should be included in retrieval.

        Args:
            note: The note to check
            threshold: Minimum importance (default: MIN_RETRIEVAL_IMPORTANCE)
            current_time: Current time for decay calculation

        Returns:
            True if note should be retrieved
        """
        threshold = threshold or MIN_RETRIEVAL_IMPORTANCE
        decayed = self.decay_importance(note, current_time)
        return decayed >= threshold

    def suggest_decay_rate(self, content: str, section: str = "") -> float:
        """
        Suggest a decay rate for a note based on its content.

        Args:
            content: The note text
            section: Section the note belongs to

        Returns:
            Suggested decay rate (lower = slower decay)
        """
        importance = self.score_note(content, section)

        # High importance notes decay slower
        if importance >= 0.8:
            return 0.005  # Very slow decay
        elif importance >= 0.5:
            return 0.01   # Slow decay
        elif importance >= 0.3:
            return 0.02   # Normal decay
        else:
            return 0.05   # Fast decay
