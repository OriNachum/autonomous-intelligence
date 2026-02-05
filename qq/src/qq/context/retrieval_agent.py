"""Context Retrieval Agent - pulls relevant context from Notes and Knowledge Graph."""

import logging
from typing import List, Dict, Any, Optional

from qq.memory.notes_agent import NotesAgent
from qq.memory.core_notes import CoreNotesManager

# We need to import dynamically or assume sys.path is set by app.py
try:
    from graph.graph import KnowledgeGraphAgent
except ImportError:
    # Fallback or optional
    KnowledgeGraphAgent = None

from qq.embeddings import EmbeddingClient

logger = logging.getLogger("qq.retrieval")


class ContextRetrievalAgent:
    """
    Agent that retrieves relevant context before each interaction.

    Pulls from:
    1. Core Notes (protected, always included)
    2. Working Notes (MongoDB with vector search)
    3. Knowledge Graph (Neo4j with embedding similarity)

    Combines results into a context injection for the system prompt.
    Also tracks access counts for importance decay.
    """

    def __init__(
        self,
        notes_agent: Optional[NotesAgent] = None,
        core_manager: Optional[CoreNotesManager] = None,
        knowledge_agent: Optional[KnowledgeGraphAgent] = None,
        embeddings: Optional[EmbeddingClient] = None,
    ):
        """
        Initialize the Context Retrieval Agent.

        Args:
            notes_agent: NotesAgent for note retrieval
            core_manager: CoreNotesManager for core note retrieval
            knowledge_agent: KnowledgeGraphAgent for entity retrieval
            embeddings: EmbeddingClient for query embedding
        """
        self.notes_agent = notes_agent
        self.core_manager = core_manager
        self.knowledge_agent = knowledge_agent
        self.embeddings = embeddings

        self._initialized = False
        self._mongo_store = None
    
    def _ensure_initialized(self) -> None:
        """Lazy initialize agents if not provided."""
        if self._initialized:
            return

        if self.notes_agent is None:
            try:
                self.notes_agent = NotesAgent()
            except Exception:
                pass

        if self.core_manager is None:
            try:
                self.core_manager = CoreNotesManager()
            except Exception:
                pass

        if self.knowledge_agent is None:
            try:
                self.knowledge_agent = KnowledgeGraphAgent()
            except Exception:
                pass

        if self.embeddings is None:
            try:
                self.embeddings = EmbeddingClient()
            except Exception:
                pass

        # Initialize MongoDB store for access tracking
        if self._mongo_store is None:
            try:
                from qq.memory.mongo_store import MongoNotesStore
                self._mongo_store = MongoNotesStore()
            except Exception:
                pass

        self._initialized = True
    
    def prepare_context(
        self,
        user_input: str,
        max_notes: int = 3,
        max_entities: int = 5,
    ) -> Dict[str, Any]:
        """
        Prepare context for the next interaction.

        Args:
            user_input: The user's current message
            max_notes: Maximum notes to retrieve
            max_entities: Maximum entities to retrieve

        Returns:
            Dict with 'core_notes', 'notes', 'entities', and 'context_text'
        """
        self._ensure_initialized()

        core_notes = {}
        notes = []
        entities = []

        # Always retrieve core notes (protected, high priority)
        if self.core_manager:
            try:
                core_notes = self.core_manager.get_all_items()
            except Exception as e:
                logger.debug(f"Could not retrieve core notes: {e}")

        # Retrieve relevant working notes
        if self.notes_agent:
            try:
                notes = self.notes_agent.get_relevant_notes(
                    query=user_input,
                    limit=max_notes,
                )
                # Track access for importance decay
                self._track_access(notes)
            except Exception as e:
                logger.debug(f"Could not retrieve notes: {e}")

        # Retrieve relevant entities
        if self.knowledge_agent:
            try:
                entities = self.knowledge_agent.get_relevant_entities(
                    query=user_input,
                    limit=max_entities,
                )
            except Exception as e:
                logger.debug(f"Could not retrieve entities: {e}")

        # Format context text for system prompt injection
        context_text = self._format_context(core_notes, notes, entities)

        return {
            "core_notes": core_notes,
            "notes": notes,
            "entities": entities,
            "context_text": context_text,
        }

    def _track_access(self, notes: List[Dict[str, Any]]) -> None:
        """
        Track access to notes for importance scoring.

        Args:
            notes: List of retrieved notes
        """
        if not self._mongo_store:
            return

        for note in notes:
            note_id = note.get("note_id")
            if note_id:
                try:
                    self._mongo_store.increment_access(note_id)
                except Exception as e:
                    logger.debug(f"Could not track access for {note_id}: {e}")
    
    def _format_context(
        self,
        core_notes: Dict[str, List[str]],
        notes: List[Dict[str, Any]],
        entities: List[Dict[str, Any]],
    ) -> str:
        """
        Format retrieved context into a text block for system prompt.

        Args:
            core_notes: Core notes organized by category
            notes: Retrieved working notes with scores
            entities: Retrieved entities with scores

        Returns:
            Formatted context text
        """
        parts = []

        # Format core notes section (always included, high priority)
        core_items = []
        for category, items in core_notes.items():
            for item in items:
                if item.strip():
                    core_items.append(f"- {item}")

        if core_items:
            parts.append("**Core Memory (User Profile):**")
            parts.extend(core_items[:10])  # Limit to avoid context bloat

        # Format working notes section
        if notes:
            note_items = []
            for note in notes:
                content = note.get("content", "")
                score = note.get("score", 0)
                if content and score > 0.3:  # Only include relevant notes
                    note_items.append(f"- {content}")

            if note_items:
                if parts:
                    parts.append("")  # Blank line separator
                parts.append("**Relevant Memory Notes:**")
                parts.extend(note_items[:5])  # Limit to top 5

        # Format entities section
        if entities:
            entity_items = []
            for entity in entities:
                name = entity.get("name", "")
                etype = entity.get("type", "")
                description = entity.get("description", "")
                score = entity.get("score", 0)

                if name and score > 0.3:  # Only include relevant entities
                    if description:
                        entity_items.append(f"- **{name}** ({etype}): {description}")
                    else:
                        entity_items.append(f"- **{name}** ({etype})")

            if entity_items:
                if parts:
                    parts.append("")  # Blank line separator
                parts.append("**Related Knowledge:**")
                parts.extend(entity_items[:5])  # Limit to top 5

        if not parts:
            return ""

        return "\n".join(parts)
    
    def inject_context(
        self,
        system_prompt: str,
        user_input: str,
    ) -> str:
        """
        Inject retrieved context into the system prompt.
        
        Args:
            system_prompt: Original system prompt
            user_input: User's current message
            
        Returns:
            System prompt with context injection
        """
        context = self.prepare_context(user_input)
        context_text = context.get("context_text", "")
        
        if not context_text:
            return system_prompt
        
        # Inject context before the main prompt content
        injection = f"""## Retrieved Context

The following information was retrieved from memory and knowledge base as potentially relevant to this conversation:

{context_text}

---

"""
        
        return injection + system_prompt
    
    def get_full_context_summary(self) -> str:
        """
        Get a summary of all available context.
        
        Returns:
            Summary of notes and knowledge graph state
        """
        self._ensure_initialized()
        
        parts = ["## Memory Context Summary\n"]
        
        # Notes summary
        if self.notes_agent:
            try:
                notes = self.notes_agent.get_all_notes()
                if notes:
                    parts.append("### Notes")
                    parts.append(notes[:500] + "..." if len(notes) > 500 else notes)
            except Exception:
                pass
        
        # Knowledge graph summary
        if self.knowledge_agent:
            try:
                summary = self.knowledge_agent.get_graph_summary()
                entity_counts = summary.get("entity_counts", {})
                rel_counts = summary.get("relationship_counts", {})
                
                if entity_counts or rel_counts:
                    parts.append("\n### Knowledge Graph")
                    if entity_counts:
                        counts = ", ".join(f"{t}: {c}" for t, c in entity_counts.items())
                        parts.append(f"Entities: {counts}")
                    if rel_counts:
                        counts = ", ".join(f"{t}: {c}" for t, c in rel_counts.items())
                        parts.append(f"Relationships: {counts}")
            except Exception:
                pass
        
        return "\n".join(parts)
