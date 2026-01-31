"""Notes Agent - summarizes conversation history and updates notes."""

import json
import hashlib
from typing import List, Dict, Any, Optional

from qq.memory.notes import NotesManager
from qq.memory.mongo_store import MongoNotesStore
from qq.embeddings import EmbeddingClient


# Prompt for summarizing history and extracting notes updates
NOTES_EXTRACTION_PROMPT = """Analyze the following conversation messages and extract key information to update memory notes.

The current notes contain these sections:
- Key Topics: Main subjects discussed
- Important Facts: Specific facts, data, or decisions
- People & Entities: Names, projects, systems mentioned
- Ongoing Threads: Unfinished discussions or pending items

Current notes content:
{current_notes}

Recent conversation:
{messages}

Based on the conversation, provide a JSON response with:
1. "additions": List of items to ADD to notes (not already present)
2. "removals": List of items to REMOVE (no longer relevant or resolved)
3. "summary": A brief 1-2 sentence summary of the key new information

Each addition should have "section" and "item" fields.
Only include genuinely new information. Do not duplicate existing notes.
If nothing significant to add, return empty lists.

Response format:
{{
  "additions": [
    {{"section": "Key Topics", "item": "..."}}
  ],
  "removals": ["pattern to remove"],
  "summary": "..."
}}

Respond with ONLY valid JSON, no other text."""


class NotesAgent:
    """
    Agent that summarizes conversation history and maintains notes.
    
    Analyzes the last N messages and incrementally updates:
    1. The notes.md file on disk
    2. MongoDB with vector embeddings
    """
    
    def __init__(
        self,
        notes_manager: Optional[NotesManager] = None,
        mongo_store: Optional[MongoNotesStore] = None,
        embeddings: Optional[EmbeddingClient] = None,
        llm_client: Any = None,
    ):
        """
        Initialize the Notes Agent.
        
        Args:
            notes_manager: NotesManager instance (created if not provided)
            mongo_store: MongoNotesStore instance (created if not provided)
            embeddings: EmbeddingClient instance (created if not provided)
            llm_client: LLM client for summarization (required for processing)
        """
        self.notes_manager = notes_manager or NotesManager()
        self.mongo_store = mongo_store
        self.embeddings = embeddings
        self.llm_client = llm_client
        
        # Lazy initialization of optional dependencies
        self._mongo_initialized = False
        self._embeddings_initialized = False
    
    def _init_mongo(self) -> None:
        """Lazy initialize MongoDB store."""
        if not self._mongo_initialized and self.mongo_store is None:
            try:
                self.mongo_store = MongoNotesStore()
                self._mongo_initialized = True
            except Exception:
                # MongoDB not available, continue without it
                pass
    
    def _init_embeddings(self) -> None:
        """Lazy initialize embeddings client."""
        if not self._embeddings_initialized and self.embeddings is None:
            try:
                self.embeddings = EmbeddingClient()
                self._embeddings_initialized = True
            except Exception:
                # TEI not available, continue without embeddings
                pass
    
    def process_messages(self, messages: List[Dict[str, str]]) -> Dict[str, Any]:
        """
        Process conversation messages and update notes.
        
        Args:
            messages: List of message dicts with 'role' and 'content'
            
        Returns:
            Dict with 'additions', 'removals', and 'summary'
        """
        if not messages or not self.llm_client:
            return {"additions": [], "removals": [], "summary": ""}
        
        # Load current notes
        current_notes = self.notes_manager.get_notes()
        
        # Format messages for prompt
        formatted_messages = "\n".join(
            f"{m['role'].upper()}: {m['content']}"
            for m in messages[-20:]  # Last 20 messages
        )
        
        # Get LLM to analyze and extract updates
        prompt = NOTES_EXTRACTION_PROMPT.format(
            current_notes=current_notes,
            messages=formatted_messages,
        )
        
        try:
            response = self.llm_client.chat(
                messages=[
                    {"role": "system", "content": "You are a precise JSON-only assistant."},
                    {"role": "user", "content": prompt},
                ],
                stream=False,
            )
            
            # Parse JSON response
            updates = json.loads(response)
            
            # Apply updates to notes file
            self._apply_updates(updates)
            
            return updates
            
        except (json.JSONDecodeError, Exception) as e:
            return {"additions": [], "removals": [], "summary": f"Error: {e}"}
    
    def _apply_updates(self, updates: Dict[str, Any]) -> None:
        """Apply extracted updates to notes file and MongoDB."""
        additions = updates.get("additions", [])
        removals = updates.get("removals", [])
        
        # Update notes.md file
        self.notes_manager.apply_diff(additions, removals)
        
        # Update MongoDB with embeddings
        self._init_mongo()
        self._init_embeddings()
        
        if self.mongo_store and self.embeddings:
            for addition in additions:
                item = addition.get("item", "")
                section = addition.get("section", "")
                
                if item:
                    # Generate ID from content hash
                    note_id = hashlib.sha256(item.encode()).hexdigest()[:16]
                    
                    # Generate embedding
                    try:
                        embedding = self.embeddings.get_embedding(item)
                        
                        # Store in MongoDB
                        self.mongo_store.upsert_note(
                            note_id=note_id,
                            content=item,
                            embedding=embedding,
                            section=section,
                        )
                    except Exception:
                        # Embedding service unavailable, store without embedding
                        self.mongo_store.upsert_note(
                            note_id=note_id,
                            content=item,
                            embedding=[],
                            section=section,
                        )
    
    def get_relevant_notes(self, query: str, limit: int = 5) -> List[Dict[str, Any]]:
        """
        Get notes relevant to a query using vector similarity.
        
        Args:
            query: Query text
            limit: Maximum notes to return
            
        Returns:
            List of relevant notes with scores
        """
        self._init_mongo()
        self._init_embeddings()
        
        if not self.mongo_store or not self.embeddings:
            # Fallback: return recent notes from file
            return [{"content": self.notes_manager.get_notes(), "score": 1.0}]
        
        try:
            query_embedding = self.embeddings.get_embedding(query)
            return self.mongo_store.search_similar(query_embedding, limit=limit)
        except Exception:
            return [{"content": self.notes_manager.get_notes(), "score": 1.0}]
    
    def get_all_notes(self) -> str:
        """Get the full notes.md content."""
        return self.notes_manager.get_notes()
