"""Context Retrieval Agent - pulls relevant context from Notes and Knowledge Graph."""

from typing import List, Dict, Any, Optional

from qq.memory.notes_agent import NotesAgent
from qq.knowledge.graph_agent import KnowledgeGraphAgent
from qq.embeddings import EmbeddingClient


class ContextRetrievalAgent:
    """
    Agent that retrieves relevant context before each interaction.
    
    Pulls from:
    1. Notes (MongoDB with vector search)
    2. Knowledge Graph (Neo4j with embedding similarity)
    
    Combines results into a context injection for the system prompt.
    """
    
    def __init__(
        self,
        notes_agent: Optional[NotesAgent] = None,
        knowledge_agent: Optional[KnowledgeGraphAgent] = None,
        embeddings: Optional[EmbeddingClient] = None,
    ):
        """
        Initialize the Context Retrieval Agent.
        
        Args:
            notes_agent: NotesAgent for note retrieval
            knowledge_agent: KnowledgeGraphAgent for entity retrieval
            embeddings: EmbeddingClient for query embedding
        """
        self.notes_agent = notes_agent
        self.knowledge_agent = knowledge_agent
        self.embeddings = embeddings
        
        self._initialized = False
    
    def _ensure_initialized(self) -> None:
        """Lazy initialize agents if not provided."""
        if self._initialized:
            return
        
        if self.notes_agent is None:
            try:
                self.notes_agent = NotesAgent()
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
            Dict with 'notes', 'entities', and 'context_text'
        """
        self._ensure_initialized()
        
        notes = []
        entities = []
        
        # Retrieve relevant notes
        if self.notes_agent:
            try:
                notes = self.notes_agent.get_relevant_notes(
                    query=user_input,
                    limit=max_notes,
                )
            except Exception:
                pass
        
        # Retrieve relevant entities
        if self.knowledge_agent:
            try:
                entities = self.knowledge_agent.get_relevant_entities(
                    query=user_input,
                    limit=max_entities,
                )
            except Exception:
                pass
        
        # Format context text for system prompt injection
        context_text = self._format_context(notes, entities)
        
        return {
            "notes": notes,
            "entities": entities,
            "context_text": context_text,
        }
    
    def _format_context(
        self,
        notes: List[Dict[str, Any]],
        entities: List[Dict[str, Any]],
    ) -> str:
        """
        Format retrieved context into a text block for system prompt.
        
        Args:
            notes: Retrieved notes with scores
            entities: Retrieved entities with scores
            
        Returns:
            Formatted context text
        """
        parts = []
        
        # Format notes section
        if notes:
            note_items = []
            for note in notes:
                content = note.get("content", "")
                score = note.get("score", 0)
                if content and score > 0.3:  # Only include relevant notes
                    note_items.append(f"- {content}")
            
            if note_items:
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
