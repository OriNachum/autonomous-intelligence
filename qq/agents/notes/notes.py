"""Notes Agent wrapper - loads role prompt and handles JSON parsing."""

import json
import hashlib
import logging
import re
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Any, Optional

from qq.memory.notes import NotesManager


# Set up logging to file
def setup_logging():
    """Configure logging for notes agent."""
    log_dir = Path(__file__).parent.parent.parent / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    log_file = log_dir / "notes_agent.log"
    
    logging.basicConfig(
        level=logging.DEBUG,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        handlers=[
            logging.FileHandler(log_file),
        ]
    )
    return logging.getLogger("notes_agent")

logger = setup_logging()


def load_role_prompt() -> str:
    """Load the notes extraction prompt from notes.system.md."""
    role_file = Path(__file__).parent / "notes.system.md"
    if role_file.exists():
        return role_file.read_text().strip()
    raise FileNotFoundError(f"Notes role prompt not found: {role_file}")


def parse_json_response(response: str) -> dict:
    """
    Parse JSON from LLM response, stripping thinking tags.
    
    Handles responses that include <think>...</think> blocks before JSON.
    """
    logger.debug(f"Raw LLM response length: {len(response)}")
    logger.debug(f"Raw response first 500 chars: {response[:500]}")
    
    # Remove <think>...</think> blocks
    cleaned = re.sub(r'<think>.*?</think>', '', response, flags=re.DOTALL)
    cleaned = cleaned.strip()
    
    logger.debug(f"Cleaned response: {cleaned[:500]}")
    
    # Try direct parse first
    try:
        result = json.loads(cleaned)
        logger.info(f"Direct JSON parse succeeded: {result}")
        return result
    except json.JSONDecodeError as e:
        logger.debug(f"Direct parse failed: {e}")
    
    # Find JSON object in response
    match = re.search(r'\{.*\}', cleaned, flags=re.DOTALL)
    if match:
        try:
            result = json.loads(match.group())
            logger.info(f"Regex JSON parse succeeded: {result}")
            return result
        except json.JSONDecodeError as e:
            logger.error(f"Regex parse failed: {e}")
    
    logger.error(f"Failed to parse JSON from response")
    return {"additions": [], "removals": [], "summary": "Failed to parse response"}


class NotesAgent:
    """
    Agent that summarizes conversation history and maintains notes.
    
    Analyzes the last N messages and incrementally updates:
    1. The notes.md file on disk
    2. MongoDB with vector embeddings (optional)
    """
    
    def __init__(
        self,
        notes_manager: Optional[NotesManager] = None,
        mongo_store: Optional[Any] = None,
        embeddings: Optional[Any] = None,
        llm_client: Any = None,
    ):
        """
        Initialize the Notes Agent.
        
        Args:
            notes_manager: NotesManager instance (created if not provided)
            mongo_store: MongoNotesStore instance (optional)
            embeddings: EmbeddingClient instance (optional)
            llm_client: LLM client for summarization (required for processing)
        """
        self.notes_manager = notes_manager or NotesManager()
        self.mongo_store = mongo_store
        self.embeddings = embeddings
        self.llm_client = llm_client
        self._role_prompt = None
        
        # Lazy initialization of optional dependencies
        self._mongo_initialized = False
        self._embeddings_initialized = False
    
    @property
    def role_prompt(self) -> str:
        """Load role prompt on first access."""
        if self._role_prompt is None:
            self._role_prompt = load_role_prompt()
        return self._role_prompt
    
    def _init_mongo(self) -> None:
        """Lazy initialize MongoDB store."""
        if not self._mongo_initialized and self.mongo_store is None:
            try:
                from qq.memory.mongo_store import MongoNotesStore
                self.mongo_store = MongoNotesStore()
                self._mongo_initialized = True
            except Exception:
                pass
    
    def _init_embeddings(self) -> None:
        """Lazy initialize embeddings client."""
        if not self._embeddings_initialized and self.embeddings is None:
            try:
                from qq.embeddings import EmbeddingClient
                self.embeddings = EmbeddingClient()
                self._embeddings_initialized = True
            except Exception:
                pass
    
    def process_messages(self, messages: List[Dict[str, str]]) -> Dict[str, Any]:
        """
        Process conversation messages and update notes.
        
        Args:
            messages: List of message dicts with 'role' and 'content'
            
        Returns:
            Dict with 'additions', 'removals', and 'summary'
        """
        logger.info(f"process_messages called with {len(messages) if messages else 0} messages")
        
        if not messages or not self.llm_client:
            logger.warning(f"Early return: messages={bool(messages)}, llm_client={bool(self.llm_client)}")
            return {"additions": [], "removals": [], "summary": ""}
        
        # Load current notes
        current_notes = self.notes_manager.get_notes()
        logger.debug(f"Current notes length: {len(current_notes)}")
        
        # Format messages for prompt
        formatted_messages = "\n".join(
            f"{m['role'].upper()}: {m['content']}"
            for m in messages[-20:]  # Last 20 messages
        )
        
        # Build prompt from role template
        prompt = self.role_prompt.format(
            current_notes=current_notes,
            messages=formatted_messages,
        )
        logger.debug(f"Prompt length: {len(prompt)}")
        
        try:
            logger.info("Calling LLM for notes extraction...")
            response = self.llm_client.chat(
                messages=[
                    {"role": "system", "content": "You are a precise JSON-only assistant. Output ONLY valid JSON."},
                    {"role": "user", "content": prompt},
                ],
                stream=False,
            )
            logger.info(f"LLM response received, length: {len(response)}")
            
            # Parse JSON response (handles <think> tags)
            updates = parse_json_response(response)
            logger.info(f"Updates parsed: {updates}")
            
            # Apply updates to notes file
            self._apply_updates(updates)
            
            return updates
            
        except Exception as e:
            logger.error(f"Exception in process_messages: {e}", exc_info=True)
            return {"additions": [], "removals": [], "summary": f"Error: {e}"}
    
    def _apply_updates(self, updates: Dict[str, Any]) -> None:
        """Apply extracted updates to notes file and MongoDB."""
        additions = updates.get("additions", [])
        removals = updates.get("removals", [])
        
        logger.info(f"Applying updates: {len(additions)} additions, {len(removals)} removals")
        
        # Update notes.md file
        self.notes_manager.apply_diff(additions, removals)
        logger.info("Notes file updated via apply_diff")
        
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
