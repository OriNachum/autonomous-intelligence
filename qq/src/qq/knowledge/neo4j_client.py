"""Neo4j client for knowledge graph storage with embeddings."""

import os
from typing import Optional, List, Dict, Any


class Neo4jClient:
    """
    Neo4j client for storing and querying knowledge graph entities.
    
    Supports entity/relationship CRUD and embedding-based similarity search.
    """
    
    def __init__(
        self,
        uri: Optional[str] = None,
        user: Optional[str] = None,
        password: Optional[str] = None,
    ):
        """
        Initialize Neo4j connection.
        
        Args:
            uri: Neo4j Bolt URI
            user: Neo4j username
            password: Neo4j password
        """
        from neo4j import GraphDatabase
        
        self.uri = uri or os.getenv("NEO4J_URI", "bolt://localhost:7687")
        self.user = user or os.getenv("NEO4J_USER", "neo4j")
        self.password = password or os.getenv("NEO4J_PASSWORD", "refinerypass")
        
        self.driver = GraphDatabase.driver(
            self.uri,
            auth=(self.user, self.password)
        )
    
    def close(self) -> None:
        """Close the driver connection."""
        self.driver.close()
    
    def execute(
        self,
        query: str,
        parameters: Optional[Dict[str, Any]] = None,
    ) -> List[Dict[str, Any]]:
        """
        Execute a Cypher query and return results.
        
        Args:
            query: Cypher query string
            parameters: Query parameters
            
        Returns:
            List of result records as dicts
        """
        with self.driver.session() as session:
            result = session.run(query, parameters or {})
            return [record.data() for record in result]
    
    def create_entity(
        self,
        entity_type: str,
        name: str,
        properties: Optional[Dict[str, Any]] = None,
        embedding: Optional[List[float]] = None,
        aliases: Optional[List[str]] = None,
        canonical_name: Optional[str] = None,
    ) -> str:
        """
        Create or update an entity node.

        Args:
            entity_type: Entity label (Person, Concept, Topic, Location, Event)
            name: Entity name (used as identifier)
            properties: Additional properties (description, notes, confidence, etc.)
            embedding: Optional vector embedding
            aliases: Optional list of alternative names for this entity
            canonical_name: Optional normalized/canonical form of the name

        Returns:
            Entity ID (the name itself)
        """
        props = properties or {}
        props["name"] = name

        if embedding:
            props["embedding"] = embedding

        if aliases:
            props["aliases"] = aliases

        if canonical_name:
            props["canonical_name"] = canonical_name

        # Build property set clause
        prop_items = ", ".join(f"n.{k} = ${k}" for k in props.keys())

        query = f"""
            MERGE (n:{entity_type} {{name: $name}})
            ON CREATE SET {prop_items},
                n.mention_count = 1,
                n.first_seen = datetime(),
                n.last_seen = datetime()
            ON MATCH SET {prop_items},
                n.mention_count = coalesce(n.mention_count, 0) + 1,
                n.last_seen = datetime()
            RETURN n.name as id
        """

        result = self.execute(query, props)
        return result[0]["id"] if result else name
    
    def create_relationship(
        self,
        source_name: str,
        target_name: str,
        relationship_type: str,
        properties: Optional[Dict[str, Any]] = None,
    ) -> bool:
        """
        Create a relationship between two entities.

        Args:
            source_name: Source entity name
            target_name: Target entity name
            relationship_type: Relationship type (e.g., KNOWS, RELATES_TO)
            properties: Optional relationship properties (description, notes, confidence, evidence)

        Returns:
            True if relationship was created
        """
        props = properties or {}

        # Build property set if any
        if props:
            prop_items = ", ".join(f"r.{k} = ${k}" for k in props.keys())
            set_clause = f"""
                ON CREATE SET {prop_items},
                    r.mention_count = 1,
                    r.first_seen = datetime(),
                    r.last_seen = datetime()
                ON MATCH SET {prop_items},
                    r.mention_count = coalesce(r.mention_count, 0) + 1,
                    r.last_seen = datetime()
            """
        else:
            set_clause = """
                ON CREATE SET r.mention_count = 1,
                    r.first_seen = datetime(),
                    r.last_seen = datetime()
                ON MATCH SET r.mention_count = coalesce(r.mention_count, 0) + 1,
                    r.last_seen = datetime()
            """

        query = f"""
            MATCH (a {{name: $source}})
            MATCH (b {{name: $target}})
            MERGE (a)-[r:{relationship_type}]->(b)
            {set_clause}
            RETURN type(r) as rel_type
        """

        params = {"source": source_name, "target": target_name, **props}
        result = self.execute(query, params)
        return len(result) > 0
    
    def get_entity(self, name: str) -> Optional[Dict[str, Any]]:
        """Get an entity by name."""
        query = """
            MATCH (n {name: $name})
            RETURN n.name as name, labels(n)[0] as type,
                   n.description as description, n.embedding as embedding
        """
        result = self.execute(query, {"name": name})
        return result[0] if result else None
    
    def search_entities_by_embedding(
        self,
        query_embedding: List[float],
        entity_type: Optional[str] = None,
        limit: int = 10,
    ) -> List[Dict[str, Any]]:
        """
        Search entities by embedding similarity.
        
        Uses cosine similarity computed in Python (for small graphs).
        
        Args:
            query_embedding: Query vector
            entity_type: Optional filter by entity type
            limit: Maximum results
            
        Returns:
            List of entities with similarity scores
        """
        import math
        
        # Fetch entities with embeddings
        if entity_type:
            query = f"MATCH (n:{entity_type}) WHERE n.embedding IS NOT NULL RETURN n"
        else:
            query = "MATCH (n) WHERE n.embedding IS NOT NULL RETURN n"
        
        results = self.execute(query)
        
        # Compute cosine similarity
        def cosine_similarity(v1: List[float], v2: List[float]) -> float:
            if not v1 or not v2:
                return 0.0
            dot_product = sum(a * b for a, b in zip(v1, v2))
            norm1 = math.sqrt(sum(a * a for a in v1))
            norm2 = math.sqrt(sum(b * b for b in v2))
            if norm1 == 0 or norm2 == 0:
                return 0.0
            return dot_product / (norm1 * norm2)
        
        scored = []
        for r in results:
            node = r["n"]
            if hasattr(node, "get"):
                embedding = node.get("embedding", [])
                if embedding:
                    score = cosine_similarity(query_embedding, list(embedding))
                    scored.append({
                        "name": node.get("name"),
                        "type": list(node.labels)[0] if hasattr(node, "labels") else None,
                        "description": node.get("description"),
                        "score": score,
                    })
        
        scored.sort(key=lambda x: x["score"], reverse=True)
        return scored[:limit]
    
    def get_related_entities(
        self,
        entity_name: str,
        depth: int = 2,
        limit: int = 20,
    ) -> List[Dict[str, Any]]:
        """
        Get entities related to a given entity up to N hops.
        
        Args:
            entity_name: Starting entity name
            depth: Maximum relationship depth
            limit: Maximum results
            
        Returns:
            List of related entities with path info
        """
        query = f"""
            MATCH (start {{name: $name}})-[r*1..{depth}]-(related)
            WHERE related.name <> $name
            RETURN DISTINCT related.name as name, 
                   labels(related)[0] as type,
                   related.description as description,
                   length(r) as distance
            ORDER BY distance
            LIMIT $limit
        """
        
        return self.execute(query, {"name": entity_name, "limit": limit})
    
    def get_graph_summary(self) -> Dict[str, Any]:
        """Get a summary of entities and relationships in the graph."""
        # Get entity counts by type
        labels_query = """
            MATCH (n)
            RETURN labels(n)[0] as type, count(n) as count
        """
        labels_result = self.execute(labels_query)
        
        # Get relationship counts
        rels_query = """
            MATCH ()-[r]->()
            RETURN type(r) as type, count(r) as count
        """
        rels_result = self.execute(rels_query)
        
        return {
            "entity_counts": {r["type"]: r["count"] for r in labels_result if r["type"]},
            "relationship_counts": {r["type"]: r["count"] for r in rels_result if r["type"]},
        }
