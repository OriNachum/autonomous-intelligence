"""Deduplication System - Finds and consolidates similar notes.

Uses embedding similarity to detect near-duplicate notes and
consolidates them to reduce memory fragmentation.
"""

import logging
import math
import os
from dataclasses import dataclass
from datetime import datetime
from typing import List, Dict, Any, Optional, Tuple

from qq.memory.importance import ScoredNote, ImportanceScorer

# Configuration
DEDUP_THRESHOLD = float(os.getenv("QQ_DEDUP_THRESHOLD", "0.85"))
MAX_WORKING_NOTES = int(os.getenv("QQ_MAX_WORKING_NOTES", "100"))

logger = logging.getLogger("qq.deduplication")


@dataclass
class DuplicatePair:
    """Represents a pair of similar notes."""
    note_a: ScoredNote
    note_b: ScoredNote
    similarity: float
    embedding_a: Optional[List[float]] = None
    embedding_b: Optional[List[float]] = None

    def get_higher_importance(self) -> ScoredNote:
        """Return the note with higher importance."""
        if self.note_a.importance >= self.note_b.importance:
            return self.note_a
        return self.note_b

    def get_lower_importance(self) -> ScoredNote:
        """Return the note with lower importance."""
        if self.note_a.importance < self.note_b.importance:
            return self.note_a
        return self.note_b


@dataclass
class ConsolidationReport:
    """Report of a consolidation pass."""
    duplicates_found: int
    notes_merged: int
    notes_archived: int
    original_count: int
    final_count: int
    timestamp: datetime


class NoteDeduplicator:
    """
    Finds and consolidates similar notes using embedding similarity.

    Works with MongoDB to find notes that are semantically similar
    and merges them to reduce redundancy.
    """

    def __init__(
        self,
        mongo_store: Optional[Any] = None,
        embeddings: Optional[Any] = None,
        similarity_threshold: float = DEDUP_THRESHOLD,
    ):
        """
        Initialize the deduplicator.

        Args:
            mongo_store: MongoNotesStore instance
            embeddings: EmbeddingClient instance
            similarity_threshold: Minimum similarity to consider as duplicate
        """
        self.mongo_store = mongo_store
        self.embeddings = embeddings
        self.similarity_threshold = similarity_threshold
        self.scorer = ImportanceScorer()
        self._initialized = False

    def _ensure_initialized(self) -> None:
        """Lazy initialize dependencies."""
        if self._initialized:
            return

        if self.mongo_store is None:
            try:
                from qq.memory.mongo_store import MongoNotesStore
                self.mongo_store = MongoNotesStore()
            except Exception as e:
                logger.warning(f"Could not initialize MongoDB: {e}")

        if self.embeddings is None:
            try:
                from qq.embeddings import EmbeddingClient
                self.embeddings = EmbeddingClient()
            except Exception as e:
                logger.warning(f"Could not initialize embeddings: {e}")

        self._initialized = True

    @staticmethod
    def cosine_similarity(v1: List[float], v2: List[float]) -> float:
        """Calculate cosine similarity between two vectors."""
        if not v1 or not v2:
            return 0.0

        dot_product = sum(a * b for a, b in zip(v1, v2))
        norm1 = math.sqrt(sum(a * a for a in v1))
        norm2 = math.sqrt(sum(b * b for b in v2))

        if norm1 == 0 or norm2 == 0:
            return 0.0

        return dot_product / (norm1 * norm2)

    def find_similar(
        self,
        threshold: Optional[float] = None,
        section: Optional[str] = None,
    ) -> List[DuplicatePair]:
        """
        Find all pairs of similar notes above threshold.

        Args:
            threshold: Similarity threshold (default: self.similarity_threshold)
            section: Optional section to limit search

        Returns:
            List of duplicate pairs with similarity scores
        """
        self._ensure_initialized()

        if not self.mongo_store:
            logger.warning("MongoDB not available for deduplication")
            return []

        threshold = threshold or self.similarity_threshold
        duplicates = []

        # Fetch all notes with embeddings
        query_filter = {}
        if section:
            query_filter["section"] = section

        notes = list(self.mongo_store.collection.find(query_filter))
        logger.info(f"Checking {len(notes)} notes for duplicates")

        # Compare all pairs (O(n^2) but acceptable for small datasets)
        for i, note_a in enumerate(notes):
            embedding_a = note_a.get("embedding", [])
            if not embedding_a:
                continue

            for note_b in notes[i + 1:]:
                embedding_b = note_b.get("embedding", [])
                if not embedding_b:
                    continue

                similarity = self.cosine_similarity(embedding_a, embedding_b)

                if similarity >= threshold:
                    # Convert to ScoredNote
                    scored_a = ScoredNote(
                        content=note_a.get("content", ""),
                        section=note_a.get("section", ""),
                        importance=note_a.get("importance", 0.5),
                        access_count=note_a.get("access_count", 0),
                        last_accessed=note_a.get("last_accessed"),
                        created_at=note_a.get("created_at", datetime.now()),
                        note_id=note_a.get("note_id"),
                    )
                    scored_b = ScoredNote(
                        content=note_b.get("content", ""),
                        section=note_b.get("section", ""),
                        importance=note_b.get("importance", 0.5),
                        access_count=note_b.get("access_count", 0),
                        last_accessed=note_b.get("last_accessed"),
                        created_at=note_b.get("created_at", datetime.now()),
                        note_id=note_b.get("note_id"),
                    )

                    duplicates.append(DuplicatePair(
                        note_a=scored_a,
                        note_b=scored_b,
                        similarity=similarity,
                        embedding_a=embedding_a,
                        embedding_b=embedding_b,
                    ))

        logger.info(f"Found {len(duplicates)} duplicate pairs")
        return duplicates

    def find_exact_duplicates(self, notes_content: List[str]) -> List[Tuple[str, str]]:
        """
        Find exact text duplicates (fast, no embeddings needed).

        Args:
            notes_content: List of note content strings

        Returns:
            List of duplicate pairs (content, content)
        """
        seen = {}
        duplicates = []

        for content in notes_content:
            # Normalize for comparison
            normalized = content.strip().lower()

            if normalized in seen:
                duplicates.append((seen[normalized], content))
            else:
                seen[normalized] = content

        return duplicates

    def consolidate(
        self,
        note_a: ScoredNote,
        note_b: ScoredNote,
        use_llm: bool = False,
        model: Optional[Any] = None,
    ) -> ScoredNote:
        """
        Consolidate two similar notes into one.

        Args:
            note_a: First note
            note_b: Second note
            use_llm: Whether to use LLM for intelligent merging
            model: Model instance for LLM merging

        Returns:
            Consolidated note
        """
        # Determine which note to keep as base
        if note_a.importance >= note_b.importance:
            primary, secondary = note_a, note_b
        else:
            primary, secondary = note_b, note_a

        if use_llm and model:
            return self._llm_consolidate(primary, secondary, model)
        else:
            return self._simple_consolidate(primary, secondary)

    def _simple_consolidate(
        self,
        primary: ScoredNote,
        secondary: ScoredNote,
    ) -> ScoredNote:
        """
        Simple consolidation - keep the primary note with combined metadata.

        Args:
            primary: Higher importance note
            secondary: Lower importance note

        Returns:
            Consolidated note
        """
        # Combine access counts
        combined_access = primary.access_count + secondary.access_count

        # Keep earliest creation date
        created_at = min(primary.created_at, secondary.created_at)

        # Keep most recent access
        last_accessed = primary.last_accessed
        if secondary.last_accessed:
            if last_accessed is None or secondary.last_accessed > last_accessed:
                last_accessed = secondary.last_accessed

        # Use slower decay rate
        decay_rate = min(primary.decay_rate, secondary.decay_rate)

        # Boost importance slightly due to recurrence
        importance = min(1.0, primary.importance + 0.05)

        return ScoredNote(
            content=primary.content,
            section=primary.section,
            importance=importance,
            access_count=combined_access,
            last_accessed=last_accessed,
            created_at=created_at,
            decay_rate=decay_rate,
            note_id=primary.note_id,
        )

    def _llm_consolidate(
        self,
        primary: ScoredNote,
        secondary: ScoredNote,
        model: Any,
    ) -> ScoredNote:
        """
        LLM-assisted consolidation - merges content intelligently.

        Args:
            primary: Higher importance note
            secondary: Lower importance note
            model: Model instance

        Returns:
            Consolidated note with merged content
        """
        from strands import Agent

        prompt = f"""Given these two similar notes, create a single consolidated note that:
- Preserves all unique information from both
- Uses precise, concise language
- Removes redundancy
- Keeps the most specific details

Note 1: "{primary.content}"
Note 2: "{secondary.content}"

Return ONLY the consolidated note text, nothing else."""

        try:
            agent = Agent(
                name="consolidator",
                system_prompt="You consolidate notes. Output ONLY the consolidated text.",
                model=model,
            )
            merged_content = str(agent(prompt)).strip()

            # Create consolidated note with merged content
            return ScoredNote(
                content=merged_content,
                section=primary.section,
                importance=min(1.0, primary.importance + 0.05),
                access_count=primary.access_count + secondary.access_count,
                last_accessed=max(
                    filter(None, [primary.last_accessed, secondary.last_accessed]),
                    default=None
                ),
                created_at=min(primary.created_at, secondary.created_at),
                decay_rate=min(primary.decay_rate, secondary.decay_rate),
                note_id=primary.note_id,
            )
        except Exception as e:
            logger.warning(f"LLM consolidation failed: {e}, using simple merge")
            return self._simple_consolidate(primary, secondary)

    def run_consolidation_pass(
        self,
        archive_manager: Optional[Any] = None,
        use_llm: bool = False,
        model: Optional[Any] = None,
    ) -> ConsolidationReport:
        """
        Run a full consolidation pass on all notes.

        Args:
            archive_manager: ArchiveManager for archiving duplicates
            use_llm: Whether to use LLM for merging
            model: Model instance for LLM merging

        Returns:
            ConsolidationReport with statistics
        """
        self._ensure_initialized()

        if not self.mongo_store:
            return ConsolidationReport(
                duplicates_found=0,
                notes_merged=0,
                notes_archived=0,
                original_count=0,
                final_count=0,
                timestamp=datetime.now(),
            )

        # Get initial count
        original_count = self.mongo_store.collection.count_documents({})

        # Find duplicates
        duplicates = self.find_similar()
        notes_merged = 0
        notes_archived = 0

        # Process duplicates
        processed_ids = set()

        for pair in duplicates:
            # Skip if either note was already processed
            if pair.note_a.note_id in processed_ids or pair.note_b.note_id in processed_ids:
                continue

            # Consolidate
            merged = self.consolidate(pair.note_a, pair.note_b, use_llm, model)

            # Update the primary note in MongoDB
            if merged.note_id:
                update_set = {
                    "content": merged.content,
                    "importance": merged.importance,
                    "access_count": merged.access_count,
                    "last_accessed": merged.last_accessed,
                    "decay_rate": merged.decay_rate,
                }

                # Merge source metadata: collect sources from both notes
                update_ops: Dict[str, Any] = {"$set": update_set}
                secondary = pair.get_lower_importance()
                sec_doc = self.mongo_store.get_note(secondary.note_id) if secondary.note_id else None
                if sec_doc and sec_doc.get("source"):
                    # Push the secondary's source into source_history on the primary
                    update_ops["$push"] = {"source_history": sec_doc["source"]}

                self.mongo_store.collection.update_one(
                    {"note_id": merged.note_id},
                    update_ops,
                )

            # Archive the secondary note
            secondary = pair.get_lower_importance()
            if secondary.note_id:
                if archive_manager:
                    archive_manager.archive_note(
                        secondary.note_id,
                        reason=f"Consolidated with {merged.note_id} (similarity: {pair.similarity:.2f})"
                    )
                    notes_archived += 1
                else:
                    # Just delete if no archive manager
                    self.mongo_store.delete_note(secondary.note_id)

                processed_ids.add(secondary.note_id)

            processed_ids.add(merged.note_id)
            notes_merged += 1

        # Get final count
        final_count = self.mongo_store.collection.count_documents({})

        return ConsolidationReport(
            duplicates_found=len(duplicates),
            notes_merged=notes_merged,
            notes_archived=notes_archived,
            original_count=original_count,
            final_count=final_count,
            timestamp=datetime.now(),
        )

    def should_consolidate(self) -> bool:
        """
        Check if consolidation is needed based on note count.

        Returns:
            True if note count exceeds MAX_WORKING_NOTES
        """
        self._ensure_initialized()

        if not self.mongo_store:
            return False

        count = self.mongo_store.collection.count_documents({})
        return count > MAX_WORKING_NOTES
