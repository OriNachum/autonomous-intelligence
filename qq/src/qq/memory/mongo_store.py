"""MongoDB store for notes with vector embeddings."""

import os
from typing import Optional, List, Dict, Any
from datetime import datetime


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
    
    def upsert_note(
        self,
        note_id: str,
        content: str,
        embedding: List[float],
        section: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> None:
        """
        Insert or update a note with its embedding.
        
        Args:
            note_id: Unique identifier for the note
            content: Note text content
            embedding: Vector embedding of the content
            section: Optional section name (Key Topics, etc.)
            metadata: Optional additional metadata
        """
        doc = {
            "note_id": note_id,
            "content": content,
            "embedding": embedding,
            "section": section,
            "metadata": metadata or {},
            "updated_at": datetime.utcnow(),
        }
        
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
