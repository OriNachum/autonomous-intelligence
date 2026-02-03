"""Knowledge Graph Agent - extracts entities and relationships from conversations using vLLM."""

import logging
from pathlib import Path
from typing import List, Dict, Any, Optional

from qq.knowledge.neo4j_client import Neo4jClient
from qq.embeddings import EmbeddingClient
from qq.agents.entity_agent.entity_agent import EntityAgent
from qq.agents.relationship_agent.relationship_agent import RelationshipAgent

# Set up logging
def setup_logging():
    """Configure logging for graph agent."""
    log_dir = Path(__file__).parent.parent.parent.parent / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    log_file = log_dir / "graph_agent.log"
    
    logging.basicConfig(
        level=logging.DEBUG,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        handlers=[
            logging.FileHandler(log_file),
            logging.StreamHandler()
        ]
    )
    return logging.getLogger("graph_agent")

logger = setup_logging()

class KnowledgeGraphAgent:
    """
    Agent that extracts entities and relationships from conversations
    and stores them in a Neo4j knowledge graph using vLLM.
    """
    
    def __init__(
        self,
        neo4j_client: Optional[Neo4jClient] = None,
        embeddings: Optional[EmbeddingClient] = None,
        model: Any = None,
    ):
        """
        Initialize the Knowledge Graph Agent.
        
        Args:
            neo4j_client: Neo4jClient instance
            embeddings: EmbeddingClient instance
            model: Model instance for extraction
        """
        self.neo4j = neo4j_client
        self.embeddings = embeddings
        self.model = model
        
        # Initialize sub-agents
        self.entity_agent = EntityAgent(model)
        self.relationship_agent = RelationshipAgent(model)
        
        self._neo4j_initialized = False
        self._embeddings_initialized = False
        
    def _init_neo4j(self) -> None:
        """Lazy initialize Neo4j client."""
        if not self._neo4j_initialized and self.neo4j is None:
            try:
                self.neo4j = Neo4jClient()
                self._neo4j_initialized = True
                logger.info("Neo4j client initialized successfully")
            except Exception as e:
                logger.error(f"Failed to initialize Neo4j client: {e}", exc_info=True)
    
    def _init_embeddings(self) -> None:
        """Lazy initialize embeddings client."""
        if not self._embeddings_initialized and self.embeddings is None:
            try:
                self.embeddings = EmbeddingClient()
                self._embeddings_initialized = True
                logger.info("Embeddings client initialized successfully")
            except Exception as e:
                logger.error(f"Failed to initialize embedding client: {e}", exc_info=True)

    def process_messages(self, messages: List[Dict[str, str]]) -> Dict[str, Any]:
        """
        Process conversation messages and update knowledge graph.
        
        Args:
            messages: List of messages
            
        Returns:
            Dict with extracted entities and relationships
        """
        if not messages:
            return {"entities": [], "relationships": []}
            
        if not self.model:
            logger.warning("Model not available, skipping extraction")
            return {"entities": [], "relationships": []}
            
        # Update clients for sub-agents in case they changed
        self.entity_agent.model = self.model
        self.relationship_agent.model = self.model

        # Step 1: Extract Entities
        entities_list = self.entity_agent.extract(messages)
        print(f"[GraphAgent] Found entities: {[e.get('name') for e in entities_list]}")

        # Step 2: Extract Relationships
        relationships = self.relationship_agent.extract(messages, entities_list)
        print(f"[GraphAgent] Found relationships: {len(relationships)}")
            
        result = {
            "entities": entities_list,
            "relationships": relationships
        }
        
        self._store_extraction(result)
        return result

    def _store_extraction(self, extraction: Dict[str, Any]) -> None:
        """Store extracted entities and relationships in Neo4j."""
        self._init_neo4j()
        self._init_embeddings()
        
        if not self.neo4j:
            logger.error("Neo4j client not available, skipping storage")
            return
        
        entities = extraction.get("entities", [])
        relationships = extraction.get("relationships", [])
        
        # Create entities with embeddings
        for entity in entities:
            entity_type = entity.get("type", "Concept")
            name = entity.get("name", "")
            description = entity.get("description", "")
            
            if not name:
                continue
            
            # Generate embedding for entity
            embedding = None
            if self.embeddings:
                try:
                    embed_text = f"{name}: {description}"
                    embedding = self.embeddings.get_embedding(embed_text)
                except Exception as e:
                    logger.warning(f"Failed to generate embedding for {name}: {e}")
            
            # Create entity in Neo4j
            try:
                self.neo4j.create_entity(
                    entity_type=entity_type,
                    name=name,
                    properties={"description": description},
                    embedding=embedding,
                )
            except Exception as e:
                logger.error(f"Failed to create entity {name}: {e}")
        
        # Create relationships
        for rel in relationships:
            source = rel.get("source", "")
            target = rel.get("target", "")
            rel_type = rel.get("type", "RELATES_TO").upper().replace(" ", "_")
            description = rel.get("description", "")
            
            if source and target:
                try:
                    self.neo4j.create_relationship(
                        source_name=source,
                        target_name=target,
                        relationship_type=rel_type,
                        properties={"description": description} if description else None,
                    )
                except Exception as e:
                    logger.error(f"Failed to create relationship {source}->{target}: {e}")

    def get_relevant_entities(self, query: str, limit: int = 10) -> List[Dict[str, Any]]:
        """Get entities relevant to a query using embedding similarity."""
        self._init_neo4j()
        self._init_embeddings()
        
        if not self.neo4j or not self.embeddings:
            return []
        
        try:
            query_embedding = self.embeddings.get_embedding(query)
            return self.neo4j.search_entities_by_embedding(
                query_embedding=query_embedding,
                limit=limit,
            )
        except Exception:
            return []
            
    def get_entity_context(self, entity_name: str, depth: int = 2) -> Dict[str, Any]:
        """Get full context for an entity including relationships."""
        self._init_neo4j()
        
        if not self.neo4j:
            return {}
        
        try:
            entity = self.neo4j.get_entity(entity_name)
            related = self.neo4j.get_related_entities(entity_name, depth=depth)
            
            return {
                "entity": entity,
                "related": related,
            }
        except Exception:
            return {}
            
    def get_graph_summary(self) -> Dict[str, Any]:
        """Get summary of the knowledge graph."""
        self._init_neo4j()
        
        if not self.neo4j:
            return {"entity_counts": {}, "relationship_counts": {}}
        
        try:
            return self.neo4j.get_graph_summary()
        except Exception:
            return {"entity_counts": {}, "relationship_counts": {}}
