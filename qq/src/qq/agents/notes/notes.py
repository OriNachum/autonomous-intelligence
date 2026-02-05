"""Notes Agent wrapper - loads role prompt and handles JSON parsing."""

import json
import hashlib
import logging
import re
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Any, Optional

from strands import Agent
from qq.memory.notes import NotesManager
from qq.memory.core_notes import CoreNotesManager, PROTECTED_CATEGORIES
from qq.memory.importance import ImportanceScorer, IMPORTANCE_LEVELS
from qq.agents.prompt_loader import get_agent_prompts

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


def parse_json_response(response: str) -> dict:
    """
    Parse JSON from LLM response, stripping thinking tags.
    
    Handles responses that include <think>...</think> blocks or other
    text before/after the JSON object.
    """
    logger.debug(f"Raw LLM response length: {len(response)}")
    logger.debug(f"Raw response first 500 chars: {response[:500]}")
    
    # Remove <think>...</think> blocks
    cleaned = re.sub(r'<think>.*?</think>', '', response, flags=re.DOTALL)
    cleaned = cleaned.strip()
    
    # Strategy 1: Try direct parse first
    try:
        result = json.loads(cleaned)
        logger.info(f"Direct JSON parse succeeded: {result}")
        return result
    except json.JSONDecodeError as e:
        logger.debug(f"Direct parse failed: {e}")
    
    # Strategy 2: Find first { and use brace counting to find matching }
    first_brace = cleaned.find('{')
    if first_brace != -1:
        brace_count = 0
        in_string = False
        escape_next = False
        
        for i, char in enumerate(cleaned[first_brace:]):
            if escape_next:
                escape_next = False
                continue
            if char == '\\':
                escape_next = True
                continue
            if char == '"' and not escape_next:
                in_string = not in_string
                continue
            if in_string:
                continue
            if char == '{':
                brace_count += 1
            elif char == '}':
                brace_count -= 1
                if brace_count == 0:
                    json_str = cleaned[first_brace:first_brace + i + 1]
                    try:
                        result = json.loads(json_str)
                        logger.info(f"Brace-matched JSON parse succeeded: {result}")
                        return result
                    except json.JSONDecodeError as e:
                        logger.debug(f"Brace-matched parse failed: {e}")
                    break
    
    # Strategy 3: Look for JSON in code block (```json ... ```)
    code_match = re.search(r'```(?:json)?\s*(\{.*?\})\s*```', cleaned, flags=re.DOTALL)
    if code_match:
        try:
            result = json.loads(code_match.group(1))
            logger.info(f"Code block JSON parse succeeded: {result}")
            return result
        except json.JSONDecodeError:
            pass
    
    logger.error(f"Failed to parse JSON from response")
    return {"additions": [], "removals": [], "summary": "Failed to parse response"}


# Maximum notes to keep in working memory
import os
MAX_WORKING_NOTES = int(os.getenv("QQ_MAX_WORKING_NOTES", "50"))


class NotesAgent:
    """
    Agent that summarizes conversation history and maintains notes.

    Analyzes the last N messages and incrementally updates:
    1. The notes.md file on disk (working memory)
    2. The core.md file (protected core notes)
    3. MongoDB with vector embeddings (optional)

    Notes are scored for importance and core notes are routed
    to protected storage that won't be forgotten.

    Automatically enforces size limits on working memory.
    """

    def __init__(
        self,
        notes_manager: Optional[NotesManager] = None,
        core_manager: Optional[CoreNotesManager] = None,
        mongo_store: Optional[Any] = None,
        embeddings: Optional[Any] = None,
        model: Any = None,
        max_notes: int = MAX_WORKING_NOTES,
    ):
        """
        Initialize the Notes Agent.

        Args:
            notes_manager: NotesManager instance (created if not provided)
            core_manager: CoreNotesManager instance (created if not provided)
            mongo_store: MongoNotesStore instance (optional)
            embeddings: EmbeddingClient instance (optional)
            model: Model instance for summarization (required for processing)
            max_notes: Maximum notes to keep in working memory
        """
        self.notes_manager = notes_manager or NotesManager()
        self.core_manager = core_manager or CoreNotesManager()
        self.importance_scorer = ImportanceScorer()
        self.mongo_store = mongo_store
        self.embeddings = embeddings
        self.model = model
        self.max_notes = max_notes

        # Lazy initialization of optional dependencies
        # Mark as initialized if already provided
        self._mongo_initialized = mongo_store is not None
        self._embeddings_initialized = embeddings is not None
    
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
        
        if not messages or not self.model:
            logger.warning(f"Early return: messages={bool(messages)}, model={bool(self.model)}")
            return {"additions": [], "removals": [], "summary": ""}
        
        # Load current notes
        current_notes = self.notes_manager.get_notes()
        logger.debug(f"Current notes length: {len(current_notes)}")
        
        # Format messages for prompt
        formatted_messages = "\n".join(
            f"{m['role'].upper()}: {m['content']}"
            for m in messages[-20:]  # Last 20 messages
        )
        
        # Load prompts dynamically
        prompts = get_agent_prompts("notes")
        if "user" not in prompts:
            logger.error("Missing user prompt for notes agent")
            return {"additions": [], "removals": [], "summary": ""}

        # Build prompt from role template (now user prompt)
        prompt = prompts["user"].format(
            current_notes=current_notes,
            messages=formatted_messages,
        )
        logger.debug(f"Prompt length: {len(prompt)}")
        
        try:
            logger.info("Calling LLM for notes extraction...")
            
            # Create a temporary agent for this extraction task
            agent = Agent(
                name="notes_extractor",
                system_prompt=prompts.get("system", "You are a precise JSON-only assistant. Output ONLY valid JSON."),
                model=self.model
            )
            
            # Get response from agent
            response = str(agent(prompt))
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
        """Apply extracted updates to notes file, core notes, and MongoDB."""
        additions = updates.get("additions", [])
        removals = updates.get("removals", [])

        logger.info(f"Applying updates: {len(additions)} additions, {len(removals)} removals")

        # Separate core notes from working notes
        core_additions = []
        working_additions = []

        for addition in additions:
            item = addition.get("item", "")
            section = addition.get("section", "")
            importance_hint = addition.get("importance", "medium")

            if not item:
                continue

            # Score importance
            importance = self.importance_scorer.score_note(item, section, importance_hint)
            addition["_importance"] = importance

            # Route to core if high importance and matches core category
            is_core_candidate, suggested_category = CoreNotesManager.is_core_candidate(item)

            if importance_hint == "core" or (importance >= 0.8 and is_core_candidate):
                # Map section to core category
                category = self._map_to_core_category(section, suggested_category)
                if category:
                    core_additions.append({
                        "content": item,
                        "category": category,
                        "importance": importance,
                    })
                    logger.info(f"Routed to core ({category}): {item[:50]}...")
                else:
                    working_additions.append(addition)
            else:
                working_additions.append(addition)

        # Apply core notes
        for core_add in core_additions:
            self.core_manager.add_core(
                content=core_add["content"],
                category=core_add["category"],
                source="auto",
            )

        # Update working notes (notes.md file)
        self.notes_manager.apply_diff(working_additions, removals)
        logger.info(f"Notes file updated: {len(working_additions)} working, {len(core_additions)} core")

        # Update MongoDB with embeddings
        self._init_mongo()
        self._init_embeddings()

        if self.mongo_store and self.embeddings:
            # Store working notes in MongoDB
            for addition in working_additions:
                item = addition.get("item", "")
                section = addition.get("section", "")
                importance = addition.get("_importance", 0.5)

                if item:
                    # Generate ID from content hash
                    note_id = hashlib.sha256(item.encode()).hexdigest()[:16]

                    # Suggest decay rate based on importance
                    decay_rate = self.importance_scorer.suggest_decay_rate(item, section)

                    # Generate embedding
                    try:
                        embedding = self.embeddings.get_embedding(item)

                        # Store in MongoDB with importance
                        self.mongo_store.upsert_note(
                            note_id=note_id,
                            content=item,
                            embedding=embedding,
                            section=section,
                            importance=importance,
                            decay_rate=decay_rate,
                        )
                    except Exception:
                        # Embedding service unavailable, store without embedding
                        self.mongo_store.upsert_note(
                            note_id=note_id,
                            content=item,
                            embedding=[],
                            section=section,
                            importance=importance,
                            decay_rate=decay_rate,
                        )

        # Enforce size limit on notes.md
        self._enforce_size_limit()

    def _map_to_core_category(self, section: str, suggested: str) -> Optional[str]:
        """Map a notes section to a core category."""
        # Direct mappings
        section_to_category = {
            "People & Entities": "Relationships",
            "Important Facts": "Identity",  # May contain identity info
        }

        if suggested and suggested in PROTECTED_CATEGORIES:
            return suggested

        if section in section_to_category:
            return section_to_category[section]

        return None

    def _enforce_size_limit(self) -> int:
        """
        Enforce maximum size limit on notes.md.

        Removes lowest-importance items to stay under max_notes.

        Returns:
            Number of items removed
        """
        all_items = self.notes_manager.get_all_items()
        current_count = len(all_items)

        if current_count <= self.max_notes:
            return 0

        logger.info(f"Notes exceed limit ({current_count} > {self.max_notes}), trimming...")

        # Score all items
        scored_items = []
        for item in all_items:
            content = item["item"].strip()
            if not content:
                continue

            importance = self.importance_scorer.score_note(content, item["section"])
            scored_items.append({
                "section": item["section"],
                "item": content,
                "importance": importance,
            })

        # Sort by importance (highest first)
        scored_items.sort(key=lambda x: x["importance"], reverse=True)

        # Keep only top max_notes
        kept_items = scored_items[:self.max_notes]

        # Rebuild notes.md
        self.notes_manager.rebuild_with_items(kept_items)

        removed = current_count - len(kept_items)
        logger.info(f"Trimmed {removed} low-importance items")

        return removed
    
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
