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
        source_id: Optional[str] = None,
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
            source_id: Optional source_id for quick provenance lookup

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

        if source_id:
            props["source_latest_id"] = source_id

        # Build property set clause
        prop_items = ", ".join(f"n.{k} = ${k}" for k in props.keys())

        # On CREATE, also set source_first_id to capture the original source
        create_extra = ""
        if source_id:
            create_extra = ", n.source_first_id = $source_latest_id"

        query = f"""
            MERGE (n:{entity_type} {{name: $name}})
            ON CREATE SET {prop_items},
                n.mention_count = 1,
                n.first_seen = datetime(),
                n.last_seen = datetime(){create_extra}
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
    
    # ------------------------------------------------------------------
    # Source node CRUD (datasource-as-node provenance tracking)
    # ------------------------------------------------------------------

    def create_source(self, source_record: Dict[str, Any]) -> str:
        """Create or update a Source node representing a datasource.

        Source nodes are NOT extracted by the LLM - they represent the
        datasource itself (file, conversation) and are created programmatically.

        Args:
            source_record: Dict from SourceRecord.to_dict()

        Returns:
            The source_id for linking entities to this source.
        """
        source_id = source_record.get("source_id", "")
        if not source_id:
            return ""

        props = {k: v for k, v in source_record.items()
                 if isinstance(v, (str, int, float, bool)) and v is not None}
        props["source_id"] = source_id

        prop_items = ", ".join(f"s.{k} = ${k}" for k in props.keys())

        query = f"""
            MERGE (s:Source {{source_id: $source_id}})
            ON CREATE SET {prop_items},
                s.created_at = datetime(),
                s.last_verified = datetime(),
                s.verified = true
            ON MATCH SET {prop_items},
                s.last_seen = datetime()
            RETURN s.source_id as id
        """

        result = self.execute(query, props)
        return result[0]["id"] if result else source_id

    def link_entity_to_source(self, entity_name: str, source_id: str) -> bool:
        """Create an EXTRACTED_FROM edge from an entity to a Source node.

        Args:
            entity_name: Name of the entity node
            source_id: source_id of the Source node

        Returns:
            True if the link was created
        """
        query = """
            MATCH (e {name: $entity_name})
            MATCH (s:Source {source_id: $source_id})
            MERGE (e)-[r:EXTRACTED_FROM]->(s)
            ON CREATE SET r.created_at = datetime()
            RETURN type(r) as rel_type
        """
        result = self.execute(query, {
            "entity_name": entity_name,
            "source_id": source_id,
        })
        return len(result) > 0

    def link_relationship_to_source(
        self,
        source_name: str,
        target_name: str,
        rel_type: str,
        source_id: str,
    ) -> bool:
        """Link a relationship's evidence back to a Source node.

        Since Neo4j can't have edges-to-edges, we create an EVIDENCES
        edge from the Source node to the target entity with metadata
        about which relationship it evidences.

        Args:
            source_name: Source entity of the relationship
            target_name: Target entity of the relationship
            rel_type: Type of the relationship being evidenced
            source_id: source_id of the Source node
        """
        query = """
            MATCH (s:Source {source_id: $source_id})
            MATCH (t {name: $target_name})
            MERGE (s)-[r:EVIDENCES {rel_source: $source_name, rel_type: $rel_type}]->(t)
            ON CREATE SET r.created_at = datetime()
            RETURN type(r) as rel_type
        """
        result = self.execute(query, {
            "source_id": source_id,
            "source_name": source_name,
            "target_name": target_name,
            "rel_type": rel_type,
        })
        return len(result) > 0

    def update_source_verification(self, source_id: str, verified: bool) -> bool:
        """Update the verification status of a Source node.

        Args:
            source_id: source_id of the Source node
            verified: Whether the checksum is still valid
        """
        query = """
            MATCH (s:Source {source_id: $source_id})
            SET s.verified = $verified, s.last_verified = datetime()
            RETURN s.source_id as id
        """
        result = self.execute(query, {
            "source_id": source_id,
            "verified": verified,
        })
        return len(result) > 0

    def get_sources_for_entity(self, entity_name: str) -> List[Dict[str, Any]]:
        """Get all Source nodes linked to an entity via EXTRACTED_FROM.

        Args:
            entity_name: Name of the entity

        Returns:
            List of source dicts with properties
        """
        query = """
            MATCH (e {name: $entity_name})-[:EXTRACTED_FROM]->(s:Source)
            RETURN s.source_id as source_id,
                   s.source_type as source_type,
                   s.file_path as file_path,
                   s.file_name as file_name,
                   s.checksum as checksum,
                   s.git_repo as git_repo,
                   s.git_commit as git_commit,
                   s.git_author as git_author,
                   s.session_id as session_id,
                   s.verified as verified
        """
        return self.execute(query, {"entity_name": entity_name})

    def update_source_mongo_link(
        self,
        source_id: str,
        note_ids: List[str],
    ) -> bool:
        """Update the mongo_note_ids on a Source node to link to MongoDB notes.

        Args:
            source_id: source_id of the Source node
            note_ids: List of MongoDB note_ids stored from this source
        """
        query = """
            MATCH (s:Source {source_id: $source_id})
            SET s.mongo_note_ids = $note_ids
            RETURN s.source_id as id
        """
        result = self.execute(query, {
            "source_id": source_id,
            "note_ids": note_ids,
        })
        return len(result) > 0

    # ------------------------------------------------------------------
    # Entity / Relationship queries
    # ------------------------------------------------------------------

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
