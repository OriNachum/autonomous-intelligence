"""Knowledge Graph Agent - extracts entities and relationships from conversations."""

import json
from typing import List, Dict, Any, Optional

from qq.knowledge.neo4j_client import Neo4jClient
from qq.embeddings import EmbeddingClient


import logging
from pathlib import Path

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
            logging.StreamHandler()  # Also print to stderr
        ]
    )
    return logging.getLogger("graph_agent")

logger = setup_logging()


# Prompt for extracting entities and relationships
# Prompt for extracting relationships given entities
RELATIONSHIP_EXTRACTION_PROMPT = """Analyze the following conversation and the provided list of entities. Identify relationships between these entities based on the conversation.

Conversation:
{messages}

Entities found:
{entities}

Relationship types:
- KNOWS: Person knows Person
- RELATES_TO: General relationship
- USES: Person uses Concept/Tool
- PART_OF: Concept is part of Concept
- CAUSES: Event causes Event/State
- WORKS_ON: Person works on Topic/Project
- LOCATED_IN: Entity located in Location

Respond with ONLY valid JSON in this format:
{{
  "relationships": [
    {{"source": "Source Entity Name", "target": "Target Entity Name", "type": "RELATES_TO", "description": "Brief description"}}
  ]
}}

Only extract genuinely significant relationships. If nothing significant, return empty list."""


class KnowledgeGraphAgent:
    """
    Agent that extracts entities and relationships from conversations
    and stores them in a Neo4j knowledge graph with embeddings.
    """
    
    def __init__(
        self,
        neo4j_client: Optional[Neo4jClient] = None,
        embeddings: Optional[EmbeddingClient] = None,
        llm_client: Any = None,
        model_name: str = "urchade/gliner_small-v2.1",
    ):
        """
        Initialize the Knowledge Graph Agent.
        
        Args:
            neo4j_client: Neo4jClient instance
            embeddings: EmbeddingClient instance
            llm_client: LLM client for entity extraction
            model_name: GLiNER model name
        """
        self.neo4j = neo4j_client
        self.embeddings = embeddings
        self.llm_client = llm_client
        self.gliner_model_name = model_name
        self.gliner = None
        
        self._neo4j_initialized = False
        self._embeddings_initialized = False
        self._gliner_initialized = False

    def _init_gliner(self) -> None:
        """Lazy initialize GLiNER model."""
        if not self._gliner_initialized and self.gliner is None:
            try:
                logger.info(f"Loading GLiNER model: {self.gliner_model_name}...")
                from gliner import GLiNER
                self.gliner = GLiNER.from_pretrained(self.gliner_model_name)
                self._gliner_initialized = True
                logger.info("GLiNER model loaded successfully")
            except Exception as e:
                logger.error(f"Failed to initialize GLiNER: {e}", exc_info=True)
    
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
            messages: List of message dicts with 'role' and 'content'
            
        Returns:
            Dict with 'entities' and 'relationships' extracted
        """
    def process_messages(self, messages: List[Dict[str, str]]) -> Dict[str, Any]:
        """
        Process conversation messages and update knowledge graph.
        
        Args:
            messages: List of message dicts with 'role' and 'content'
            
        Returns:
            Dict with 'entities' and 'relationships' extracted
        """
        if not messages:
            return {"entities": [], "relationships": []}
        
        # Initialize GLiNER
        self._init_gliner()
        
        if not self.gliner:
            logger.warning("GLiNER not initialized, skipping extraction")
            return {"entities": [], "relationships": []}

        # 1. Prepare text for GLiNER (last 20 messages)
        recent_messages = messages[-20:]
        combined_text = "\n".join([f"{m['role'].upper()}: {m['content']}" for m in recent_messages])
        
        # 2. Extract Entities with GLiNER
        labels = ["Person", "Concept", "Topic", "Location", "Event"]
        
        try:
            logger.info("Extracting entities with GLiNER...")
            # GLiNER works best on sentences/paragraphs. We'll pass the whole block.
            gliner_entities = self.gliner.predict_entities(combined_text, labels, threshold=0.3)
            
            # Deduplicate and format entities
            unique_entities = {}
            for ent in gliner_entities:
                name = ent["text"].strip()
                if not name or len(name) < 2:
                    continue
                # Simple dedup by name
                if name not in unique_entities:
                    unique_entities[name] = {
                        "type": ent["label"],
                        "name": name,
                        "description": f"Extracted from conversation as {ent['label']}"
                    }
            
            entities_list = list(unique_entities.values())
            logger.info(f"GLiNER found {len(entities_list)} entities")
            
            if not entities_list:
                return {"entities": [], "relationships": []}
                
        except Exception as e:
            logger.error(f"GLiNER extraction failed: {e}", exc_info=True)
            return {"entities": [], "relationships": []}

        # 3. Extract Relationships with LLM
        if not self.llm_client:
             # If no LLM, just return entities
            self._store_extraction({"entities": entities_list, "relationships": []})
            return {"entities": entities_list, "relationships": []}

        # Format inputs for LLM
        formatted_messages = combined_text
        formatted_entities = json.dumps([{"name": e["name"], "type": e["type"]} for e in entities_list], indent=2)
        
        prompt = RELATIONSHIP_EXTRACTION_PROMPT.format(
            messages=formatted_messages,
            entities=formatted_entities
        )
        
        try:
            logger.info("Requesting relationship extraction from LLM...")
            response = self.llm_client.chat(
                messages=[
                    {"role": "system", "content": "You are a precise JSON-only assistant."},
                    {"role": "user", "content": prompt},
                ],
                stream=False,
            )
            
            # Parse JSON response
            logger.debug("Received LLM response, parsing JSON...")
            # Clean potential markdown code blocks
            response_clean = response.strip()
            if response_clean.startswith("```json"):
                response_clean = response_clean[7:]
            if response_clean.endswith("```"):
                response_clean = response_clean[:-3]
            
            relationships = []
            if response_clean.strip():
                try:
                    llm_data = json.loads(response_clean)
                    relationships = llm_data.get("relationships", [])
                except json.JSONDecodeError:
                    logger.warning(f"Failed to parse LLM JSON: {response_clean}")
            
            logger.info(f"Extraction result: {len(entities_list)} entities, {len(relationships)} relationships")
            
            result = {
                "entities": entities_list,
                "relationships": relationships
            }
            
            # Store in Neo4j
            self._store_extraction(result)
            
            return result
            
        except Exception as e:
            logger.error(f"Error during relationship extraction: {e}", exc_info=True)
            # Return at least the entities
            self._store_extraction({"entities": entities_list, "relationships": []})
            return {"entities": entities_list, "relationships": []}
    
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
    
    def get_relevant_entities(
        self,
        query: str,
        limit: int = 10,
    ) -> List[Dict[str, Any]]:
        """
        Get entities relevant to a query using embedding similarity.
        
        Args:
            query: Query text
            limit: Maximum entities to return
            
        Returns:
            List of relevant entities with scores
        """
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
    
    def get_entity_context(
        self,
        entity_name: str,
        depth: int = 2,
    ) -> Dict[str, Any]:
        """
        Get full context for an entity including relationships.
        
        Args:
            entity_name: Entity to get context for
            depth: Relationship traversal depth
            
        Returns:
            Entity details and related entities
        """
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
