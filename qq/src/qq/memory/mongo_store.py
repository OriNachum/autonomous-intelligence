"""MongoDB store for notes with vector embeddings and importance tracking."""

import os
from typing import Optional, List, Dict, Any
from datetime import datetime

# Default importance for new notes
DEFAULT_IMPORTANCE = 0.5
DEFAULT_DECAY_RATE = 0.01


class MongoNotesStore:
    """
    MongoDB storage for notes with vector embeddings.
    
    Stores notes with their embeddings for similarity search.
    Uses a simple vector similarity approach compatible with
    MongoDB's $vectorSearch or manual cosine similarity.
    """
    
    def __init__(
        self,
        uri: Optional[str] = None,
        database: str = "qq_memory",
        collection: str = "notes",
    ):
        """
        Initialize MongoDB connection.
        
        Args:
            uri: MongoDB connection URI
            database: Database name
            collection: Collection name for notes
        """
        from pymongo import MongoClient
        
        self.uri = uri or os.getenv("MONGODB_URI", "mongodb://localhost:27017")
        self.client = MongoClient(self.uri)
        self.db = self.client[database]
        self.collection = self.db[collection]
        
        # Create index for vector search if not exists
        self._ensure_indexes()
    
    def _ensure_indexes(self) -> None:
        """Ensure required indexes exist."""
        # Index on note_id for fast lookups
        self.collection.create_index("note_id", unique=True)
        # Index on section for filtering
        self.collection.create_index("section")
        # Index on updated_at for recency
        self.collection.create_index("updated_at")
        # Index on importance for filtering low-importance notes
        self.collection.create_index("importance")
        # Index on last_accessed for staleness queries
        self.collection.create_index("last_accessed")
    
    def upsert_note(
        self,
        note_id: str,
        content: str,
        embedding: List[float],
        section: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
        importance: Optional[float] = None,
        decay_rate: Optional[float] = None,
    ) -> None:
        """
        Insert or update a note with its embedding.

        Args:
            note_id: Unique identifier for the note
            content: Note text content
            embedding: Vector embedding of the content
            section: Optional section name (Key Topics, etc.)
            metadata: Optional additional metadata
            importance: Importance score (0.0-1.0)
            decay_rate: How fast importance decays
        """
        now = datetime.utcnow()

        # Check if this is a new note or update
        existing = self.collection.find_one({"note_id": note_id})

        doc = {
            "note_id": note_id,
            "content": content,
            "embedding": embedding,
            "section": section,
            "metadata": metadata or {},
            "updated_at": now,
        }

        # Add importance fields
        if importance is not None:
            doc["importance"] = importance
        elif existing is None:
            doc["importance"] = DEFAULT_IMPORTANCE

        if decay_rate is not None:
            doc["decay_rate"] = decay_rate
        elif existing is None:
            doc["decay_rate"] = DEFAULT_DECAY_RATE

        # Set created_at only for new notes
        if existing is None:
            doc["created_at"] = now
            doc["access_count"] = 0
            doc["last_accessed"] = None

        self.collection.update_one(
            {"note_id": note_id},
            {"$set": doc},
            upsert=True,
        )
    
    def get_note(self, note_id: str) -> Optional[Dict[str, Any]]:
        """Get a note by ID."""
        return self.collection.find_one({"note_id": note_id})
    
    def delete_note(self, note_id: str) -> bool:
        """
        Delete a note by ID.
        
        Returns:
            True if note was deleted
        """
        result = self.collection.delete_one({"note_id": note_id})
        return result.deleted_count > 0
    
    def search_similar(
        self,
        query_embedding: List[float],
        limit: int = 5,
        section: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """
        Search for notes similar to query using cosine similarity.
        
        This is a simple implementation that computes similarity in Python.
        For production, use MongoDB Atlas Vector Search.
        
        Args:
            query_embedding: Query vector
            limit: Maximum results to return
            section: Optional filter by section
            
        Returns:
            List of similar notes with scores
        """
        import math
        
        # Build query filter
        query_filter = {}
        if section:
            query_filter["section"] = section
        
        # Fetch all notes (for small datasets; use Atlas Vector Search for scale)
        notes = list(self.collection.find(query_filter))
        
        # Calculate cosine similarity
        def cosine_similarity(v1: List[float], v2: List[float]) -> float:
            dot_product = sum(a * b for a, b in zip(v1, v2))
            norm1 = math.sqrt(sum(a * a for a in v1))
            norm2 = math.sqrt(sum(b * b for b in v2))
            if norm1 == 0 or norm2 == 0:
                return 0.0
            return dot_product / (norm1 * norm2)
        
        # Score and sort notes
        scored = []
        for note in notes:
            if "embedding" in note and note["embedding"]:
                score = cosine_similarity(query_embedding, note["embedding"])
                scored.append({
                    "note_id": note["note_id"],
                    "content": note["content"],
                    "section": note.get("section"),
                    "score": score,
                    "metadata": note.get("metadata", {}),
                })
        
        # Sort by similarity score descending
        scored.sort(key=lambda x: x["score"], reverse=True)
        
        return scored[:limit]
    
    def get_recent_notes(
        self,
        limit: int = 10,
        section: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """
        Get most recently updated notes.
        
        Args:
            limit: Maximum results
            section: Optional filter by section
            
        Returns:
            List of recent notes
        """
        query_filter = {}
        if section:
            query_filter["section"] = section
        
        cursor = (
            self.collection
            .find(query_filter)
            .sort("updated_at", -1)
            .limit(limit)
        )
        
        return [
            {
                "note_id": doc["note_id"],
                "content": doc["content"],
                "section": doc.get("section"),
                "updated_at": doc.get("updated_at"),
            }
            for doc in cursor
        ]
    
    def clear_all(self) -> int:
        """
        Clear all notes from collection.

        Returns:
            Number of deleted documents
        """
        result = self.collection.delete_many({})
        return result.deleted_count

    def increment_access(self, note_id: str) -> bool:
        """
        Increment access count and update last_accessed timestamp.

        Args:
            note_id: ID of the note

        Returns:
            True if note was updated
        """
        result = self.collection.update_one(
            {"note_id": note_id},
            {
                "$inc": {"access_count": 1},
                "$set": {"last_accessed": datetime.utcnow()},
            }
        )
        return result.modified_count > 0

    def update_importance(self, note_id: str, importance: float) -> bool:
        """
        Update the importance score of a note.

        Args:
            note_id: ID of the note
            importance: New importance score (0.0-1.0)

        Returns:
            True if note was updated
        """
        importance = max(0.0, min(1.0, importance))
        result = self.collection.update_one(
            {"note_id": note_id},
            {"$set": {"importance": importance, "updated_at": datetime.utcnow()}}
        )
        return result.modified_count > 0

    def get_by_importance_range(
        self,
        min_importance: float = 0.0,
        max_importance: float = 1.0,
        limit: int = 100,
    ) -> List[Dict[str, Any]]:
        """
        Get notes within an importance range.

        Args:
            min_importance: Minimum importance (inclusive)
            max_importance: Maximum importance (inclusive)
            limit: Maximum results

        Returns:
            List of notes within the range
        """
        cursor = (
            self.collection
            .find({
                "importance": {"$gte": min_importance, "$lte": max_importance}
            })
            .sort("importance", -1)
            .limit(limit)
        )

        return [
            {
                "note_id": doc["note_id"],
                "content": doc["content"],
                "section": doc.get("section"),
                "importance": doc.get("importance", DEFAULT_IMPORTANCE),
                "access_count": doc.get("access_count", 0),
                "last_accessed": doc.get("last_accessed"),
                "created_at": doc.get("created_at"),
            }
            for doc in cursor
        ]

    def get_stale_notes(
        self,
        days_threshold: int = 30,
        limit: int = 50,
    ) -> List[Dict[str, Any]]:
        """
        Get notes that haven't been accessed recently.

        Args:
            days_threshold: Days since last access to consider stale
            limit: Maximum results

        Returns:
            List of stale notes
        """
        from datetime import timedelta
        cutoff = datetime.utcnow() - timedelta(days=days_threshold)

        # Notes that have never been accessed or accessed before cutoff
        cursor = (
            self.collection
            .find({
                "$or": [
                    {"last_accessed": None},
                    {"last_accessed": {"$lt": cutoff}},
                ]
            })
            .sort("importance", 1)  # Lowest importance first
            .limit(limit)
        )

        return [
            {
                "note_id": doc["note_id"],
                "content": doc["content"],
                "section": doc.get("section"),
                "importance": doc.get("importance", DEFAULT_IMPORTANCE),
                "access_count": doc.get("access_count", 0),
                "last_accessed": doc.get("last_accessed"),
                "created_at": doc.get("created_at"),
            }
            for doc in cursor
        ]

    def bulk_update_importance(
        self,
        updates: List[Dict[str, Any]],
    ) -> int:
        """
        Bulk update importance scores.

        Args:
            updates: List of {"note_id": str, "importance": float}

        Returns:
            Number of notes updated
        """
        from pymongo import UpdateOne

        if not updates:
            return 0

        operations = [
            UpdateOne(
                {"note_id": u["note_id"]},
                {"$set": {"importance": u["importance"], "updated_at": datetime.utcnow()}}
            )
            for u in updates
        ]

        result = self.collection.bulk_write(operations)
        return result.modified_count
