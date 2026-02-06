"""Notes Agent - summarizes conversation history and updates notes."""

import json
import hashlib
import re
import logging
from typing import List, Dict, Any, Optional

from qq.memory.notes import NotesManager
from qq.memory.mongo_store import MongoNotesStore
from qq.embeddings import EmbeddingClient

logger = logging.getLogger(__name__)


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
    
    def _extract_json(self, response: str) -> Dict[str, Any]:
        """
        Extract JSON from LLM response that may include thinking text.
        
        Some models prefix their JSON output with reasoning text. This method
        attempts multiple strategies to extract the JSON:
        1. Direct parse (if response is pure JSON)
        2. Find JSON object starting with {
        3. Regex-based extraction
        """
        # Strategy 1: Try direct parse first
        try:
            return json.loads(response.strip())
        except json.JSONDecodeError:
            pass
        
        # Strategy 2: Find the first { and try to parse from there
        first_brace = response.find('{')
        if first_brace != -1:
            # Find matching closing brace
            brace_count = 0
            for i, char in enumerate(response[first_brace:]):
                if char == '{':
                    brace_count += 1
                elif char == '}':
                    brace_count -= 1
                    if brace_count == 0:
                        json_str = response[first_brace:first_brace + i + 1]
                        try:
                            return json.loads(json_str)
                        except json.JSONDecodeError:
                            break
        
        # Strategy 3: Use regex to find JSON-like structure
        json_pattern = r'\{[^{}]*(?:\{[^{}]*\}[^{}]*)*\}'
        matches = re.findall(json_pattern, response)
        for match in matches:
            try:
                result = json.loads(match)
                if isinstance(result, dict) and 'additions' in result:
                    return result
            except json.JSONDecodeError:
                continue
        
        # Return default if all strategies fail
        logger.warning(f"Failed to extract JSON from response: {response[:200]}...")
        return {"additions": [], "removals": [], "summary": "Failed to parse LLM response"}
    
    def process_messages(
        self,
        messages: List[Dict[str, str]],
        file_sources: Optional[Dict[str, Any]] = None,
        session_id: Optional[str] = None,
        agent_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Process conversation messages and update notes.

        Args:
            messages: List of message dicts with 'role' and 'content'
            file_sources: Registry of file path -> SourceRecord.to_dict()
            session_id: Current session ID for provenance
            agent_id: Current agent ID for provenance

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
                    {"role": "system", "content": "You are a precise JSON-only assistant. Output ONLY valid JSON with no additional text."},
                    {"role": "user", "content": prompt},
                ],
                stream=False,
            )

            logger.debug(f"LLM response length: {len(response)}")

            # Extract JSON from response (handles thinking text)
            updates = self._extract_json(response)

            # Apply updates to notes file
            if updates.get("additions") or updates.get("removals"):
                self._apply_updates(
                    updates,
                    file_sources=file_sources,
                    session_id=session_id,
                    agent_id=agent_id,
                )
                logger.info(f"Applied updates: {len(updates.get('additions', []))} additions, {len(updates.get('removals', []))} removals")

            return updates

        except Exception as e:
            logger.error(f"Error processing messages: {e}")
            return {"additions": [], "removals": [], "summary": f"Error: {e}"}
    
    def _apply_updates(
        self,
        updates: Dict[str, Any],
        file_sources: Optional[Dict[str, Any]] = None,
        session_id: Optional[str] = None,
        agent_id: Optional[str] = None,
    ) -> None:
        """Apply extracted updates to notes file and MongoDB.

        Args:
            updates: Dict with additions, removals, summary
            file_sources: Registry of file path -> SourceRecord.to_dict()
                          from files read in this session
            session_id: Current session ID for conversation source
            agent_id: Current agent ID for conversation source
        """
        additions = updates.get("additions", [])
        removals = updates.get("removals", [])

        # Update notes.md file
        self.notes_manager.apply_diff(additions, removals)

        # Build default conversation source for notes not tied to a file
        source_dict = None
        if session_id or agent_id:
            from qq.memory.source import collect_conversation_source
            source_dict = collect_conversation_source(session_id, agent_id).to_dict()

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

                    # Determine source: check if LLM tagged a source_file
                    note_source = source_dict
                    source_file = addition.get("source_file")
                    if source_file and file_sources and source_file in file_sources:
                        note_source = file_sources[source_file]

                    # Generate embedding
                    try:
                        embedding = self.embeddings.get_embedding(item)

                        # Store in MongoDB
                        self.mongo_store.upsert_note(
                            note_id=note_id,
                            content=item,
                            embedding=embedding,
                            section=section,
                            source=note_source,
                        )
                    except Exception:
                        # Embedding service unavailable, store without embedding
                        self.mongo_store.upsert_note(
                            note_id=note_id,
                            content=item,
                            embedding=[],
                            section=section,
                            source=note_source,
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
