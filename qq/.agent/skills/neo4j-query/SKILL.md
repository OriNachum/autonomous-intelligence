---
name: neo4j-query
description: Query Neo4j knowledge graph for entities, relationships, and graph analysis.
triggers:
  - neo4j
  - knowledge graph
  - entities
  - relationships
  - graph query
  - cypher
---

# Neo4j Query Skill

Query the Neo4j knowledge graph to investigate entities, relationships, and graph structure.

## Connection Details

- **URI**: `bolt://localhost:7687` (or `NEO4J_URI` env var)
- **User**: `neo4j` (or `NEO4J_USER` env var)
- **Password**: `refinerypass` (or `NEO4J_PASSWORD` env var)

## Python Usage

```python
from qq.knowledge.neo4j_client import Neo4jClient

# Initialize client
client = Neo4jClient()

# Execute raw Cypher query
results = client.execute("MATCH (n) RETURN n LIMIT 10")

# Get graph summary (entity and relationship counts by type)
summary = client.get_graph_summary()

# Get entity by name
entity = client.get_entity("entity_name")

# Get related entities (up to N hops)
related = client.get_related_entities("entity_name", depth=2, limit=20)

# Close when done
client.close()
```

## Common Cypher Queries

### Count entities and relationships
```cypher
-- Total entities
MATCH (n) RETURN count(n) as total_entities

-- Entities by type
MATCH (n) RETURN labels(n)[0] as type, count(n) as count ORDER BY count DESC

-- Total relationships
MATCH ()-[r]->() RETURN count(r) as total_relationships

-- Relationships by type
MATCH ()-[r]->() RETURN type(r) as type, count(r) as count ORDER BY count DESC
```

### Find orphan entities (no relationships)
```cypher
-- Entities with no incoming or outgoing relationships
MATCH (n) WHERE NOT (n)--() RETURN n.name, labels(n)[0] as type
```

### Analyze connectivity
```cypher
-- Entities with most connections
MATCH (n)-[r]-() RETURN n.name, labels(n)[0] as type, count(r) as connections ORDER BY connections DESC LIMIT 10

-- Distribution of relationship counts per entity
MATCH (n)
OPTIONAL MATCH (n)-[r]-()
WITH n, count(r) as rel_count
RETURN rel_count, count(n) as entities_with_this_count ORDER BY rel_count
```

### Sample entities and relationships
```cypher
-- Sample entities with their properties
MATCH (n) RETURN n.name, labels(n)[0] as type, n.description LIMIT 20

-- Sample relationships with endpoints
MATCH (a)-[r]->(b) RETURN a.name, type(r), b.name LIMIT 20
```

## CLI Usage

```bash
# Use cypher-shell directly
docker exec -it qq-neo4j-1 cypher-shell -u neo4j -p refinerypass "MATCH (n) RETURN count(n)"
```
