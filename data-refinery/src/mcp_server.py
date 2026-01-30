"""FastMCP server for accessing Neo4j graph database."""
import os
from typing import List, Optional, Dict, Any

from fastmcp import FastMCP, Context
from neo4j import GraphDatabase


# Configuration from environment
NEO4J_URI = os.getenv("NEO4J_URI", "bolt://localhost:7687")
NEO4J_USER = os.getenv("NEO4J_USER", "neo4j")
NEO4J_PASSWORD = os.getenv("NEO4J_PASSWORD", "refinerypass")

# Create FastMCP server
mcp = FastMCP(name="DataRefineryNeo4j")


class Neo4jClient:
    """Simple Neo4j client for executing queries."""
    
    def __init__(self, uri: str, user: str, password: str):
        self.driver = GraphDatabase.driver(uri, auth=(user, password))
    
    def close(self):
        self.driver.close()
    
    def execute(self, query: str, parameters: dict = None) -> List[Dict[str, Any]]:
        """Execute a Cypher query and return results."""
        with self.driver.session() as session:
            result = session.run(query, parameters or {})
            return [record.data() for record in result]


# Global client (initialized lazily)
_client: Optional[Neo4jClient] = None


def get_client() -> Neo4jClient:
    """Get or create Neo4j client."""
    global _client
    if _client is None:
        _client = Neo4jClient(NEO4J_URI, NEO4J_USER, NEO4J_PASSWORD)
    return _client


@mcp.tool
def get_graph_schema() -> Dict[str, Any]:
    """
    Get the schema of the graph database.
    
    Returns entity types (labels) and relationship types in the database.
    """
    client = get_client()
    
    # Get node labels
    labels_result = client.execute("CALL db.labels()")
    labels = [r.get("label") for r in labels_result]
    
    # Get relationship types
    rel_types_result = client.execute("CALL db.relationshipTypes()")
    rel_types = [r.get("relationshipType") for r in rel_types_result]
    
    # Get counts
    counts = {}
    for label in labels:
        count_result = client.execute(f"MATCH (n:{label}) RETURN count(n) as count")
        counts[label] = count_result[0]["count"] if count_result else 0
    
    return {
        "entity_types": labels,
        "relationship_types": rel_types,
        "entity_counts": counts,
    }


@mcp.tool
def query_entities(
    entity_type: Optional[str] = None,
    name_pattern: Optional[str] = None,
    limit: int = 20,
) -> List[Dict[str, Any]]:
    """
    Search for entities in the graph.
    
    Args:
        entity_type: Filter by entity type (Name, Concept, Feature, Location)
        name_pattern: Filter by name pattern (case-insensitive contains)
        limit: Maximum number of results to return (default: 20)
    
    Returns:
        List of matching entities with their properties
    """
    client = get_client()
    
    # Build query
    if entity_type:
        match_clause = f"MATCH (n:{entity_type})"
    else:
        match_clause = "MATCH (n)"
    
    where_clauses = []
    params = {"limit": limit}
    
    if name_pattern:
        where_clauses.append("toLower(n.name) CONTAINS toLower($name_pattern)")
        params["name_pattern"] = name_pattern
    
    where_clause = f"WHERE {' AND '.join(where_clauses)}" if where_clauses else ""
    
    query = f"""
        {match_clause}
        {where_clause}
        RETURN n.id as id, n.name as name, labels(n)[0] as type, 
               n.description as description, n.source_page as source_page
        LIMIT $limit
    """
    
    return client.execute(query, params)


@mcp.tool
def get_entity_by_id(entity_id: str) -> Optional[Dict[str, Any]]:
    """
    Get a specific entity by its ID.
    
    Args:
        entity_id: The unique ID of the entity
    
    Returns:
        Entity properties or None if not found
    """
    client = get_client()
    
    query = """
        MATCH (n {id: $entity_id})
        RETURN n.id as id, n.name as name, labels(n)[0] as type,
               n.description as description, n.source_page as source_page
    """
    
    results = client.execute(query, {"entity_id": entity_id})
    return results[0] if results else None


@mcp.tool
def get_related_entities(
    entity_id: str,
    relationship_type: Optional[str] = None,
    direction: str = "both",
    limit: int = 20,
) -> List[Dict[str, Any]]:
    """
    Get entities related to a given entity.
    
    Args:
        entity_id: ID of the source entity
        relationship_type: Optional filter by relationship type
        direction: Direction of relationships ("in", "out", or "both")
        limit: Maximum number of results
    
    Returns:
        List of related entities with relationship info
    """
    client = get_client()
    
    rel_pattern = f":{relationship_type}" if relationship_type else ""
    
    if direction == "out":
        match = f"MATCH (n {{id: $entity_id}})-[r{rel_pattern}]->(m)"
    elif direction == "in":
        match = f"MATCH (n {{id: $entity_id}})<-[r{rel_pattern}]-(m)"
    else:
        match = f"MATCH (n {{id: $entity_id}})-[r{rel_pattern}]-(m)"
    
    query = f"""
        {match}
        RETURN m.id as id, m.name as name, labels(m)[0] as type,
               m.description as description,
               type(r) as relationship_type, r.description as relationship_description
        LIMIT $limit
    """
    
    return client.execute(query, {"entity_id": entity_id, "limit": limit})


@mcp.tool
def query_relationships(
    source_type: Optional[str] = None,
    target_type: Optional[str] = None,
    relationship_type: Optional[str] = None,
    limit: int = 20,
) -> List[Dict[str, Any]]:
    """
    Query relationships between entities.
    
    Args:
        source_type: Filter source entity by type
        target_type: Filter target entity by type
        relationship_type: Filter by relationship type
        limit: Maximum number of results
    
    Returns:
        List of relationships with source and target info
    """
    client = get_client()
    
    source = f"(a:{source_type})" if source_type else "(a)"
    target = f"(b:{target_type})" if target_type else "(b)"
    rel = f"[r:{relationship_type}]" if relationship_type else "[r]"
    
    query = f"""
        MATCH {source}-{rel}->{target}
        RETURN a.id as source_id, a.name as source_name, labels(a)[0] as source_type,
               type(r) as relationship_type, r.description as relationship_description,
               b.id as target_id, b.name as target_name, labels(b)[0] as target_type
        LIMIT $limit
    """
    
    return client.execute(query, {"limit": limit})


@mcp.tool
def run_cypher(query: str, limit: int = 50) -> List[Dict[str, Any]]:
    """
    Execute a raw Cypher query (read-only, with result limit).
    
    Args:
        query: Cypher query to execute
        limit: Maximum number of results to return (safety limit)
    
    Returns:
        Query results as a list of dictionaries
    
    Note:
        This tool only allows read operations (no CREATE, MERGE, DELETE, SET).
    """
    client = get_client()
    
    # Safety check - only allow read operations
    query_upper = query.upper()
    forbidden = ["CREATE", "MERGE", "DELETE", "SET", "REMOVE", "DROP", "CALL"]
    for word in forbidden:
        if word in query_upper:
            return [{"error": f"Write operations ({word}) are not allowed. Use read-only queries."}]
    
    # Add limit if not present
    if "LIMIT" not in query_upper:
        query = f"{query} LIMIT {limit}"
    
    try:
        return client.execute(query)
    except Exception as e:
        return [{"error": str(e)}]


def main():
    """Run the MCP server."""
    import sys
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
