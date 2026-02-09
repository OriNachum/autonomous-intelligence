# Neo4j Knowledge Graph Reference

Entity and relationship storage with embedding-based search and source provenance.

## Table of Contents

- [Neo4jClient](#neo4jclient)
- [Entity Operations](#entity-operations)
- [Relationship Operations](#relationship-operations)
- [Source Provenance](#source-provenance)
- [Graph Queries](#graph-queries)
- [Merge Entities](#merge-entities)
- [KnowledgeGraphAgent](#knowledgegraphagent)
- [Common Cypher Queries](#common-cypher-queries)

## Neo4jClient

```python
from qq.knowledge.neo4j_client import Neo4jClient

client = Neo4jClient(
    uri="bolt://localhost:7687",   # or NEO4J_URI env var
    user="neo4j",                   # or NEO4J_USER env var
    password="refinerypass"         # or NEO4J_PASSWORD env var
)
```

## Entity Operations

### Create

```python
client.create_entity(
    entity_type: str,        # Person, Concept, Topic, Location, Event
    name: str,               # Primary identifier
    properties: dict = None, # {description, notes, confidence, ...}
    embedding: List[float] = None,
    aliases: List[str] = None,
    canonical_name: str = None,
    source_id: str = None
) -> str  # Returns entity name
```

Entity types: `Person`, `Concept`, `Topic`, `Location`, `Event`.

Entity properties:
- `name`, `description`, `notes`, `confidence`
- `aliases` (list), `canonical_name`
- `mention_count`, `first_seen`, `last_seen`
- `source_first_id`, `source_latest_id`
- `embedding` (list of floats)

### Read

```python
client.get_entity(name: str) -> Optional[Dict]
# Returns entity properties or None
```

### Reinforce

```python
client.increment_mention_count(entity_name: str) -> bool
# Bumps mention_count, updates last_seen
```

### Search

```python
client.search_entities_by_embedding(
    query_embedding: List[float],
    entity_type: str = None,
    limit: int = 10
) -> List[Dict]
# Returns entities sorted by cosine similarity
```

```python
client.get_related_entities(
    entity_name: str,
    depth: int = 2,
    limit: int = 20
) -> List[Dict]
# Traverse relationships up to N hops
```

## Relationship Operations

```python
client.create_relationship(
    source_name: str,
    target_name: str,
    relationship_type: str,
    properties: dict = None  # {description, notes, confidence, evidence, ...}
) -> bool
```

Relationship properties:
- `description`, `notes`, `confidence`, `evidence`
- `mention_count`, `first_seen`, `last_seen`

## Source Provenance

Track where entities and relationships were extracted from.

```python
client.create_source(source_record: Dict) -> str
# Create a Source node. Returns source_id.
# source_record: {source_type, file_path, session_id, ...}
```

```python
client.link_entity_to_source(entity_name: str, source_id: str) -> bool
# Creates EXTRACTED_FROM relationship: entity -> source
```

```python
client.link_relationship_to_source(
    source: str,
    target: str,
    rel_type: str,
    source_id: str
) -> bool
# Creates EVIDENCES relationship: source -> relationship
```

```python
client.get_sources_for_entity(entity_name: str) -> List[Dict]
```

```python
client.update_source_verification(source_id: str, verified: bool) -> bool
```

```python
client.update_source_mongo_link(source_id: str, note_ids: List[str]) -> bool
# Link source to MongoDB note IDs for cross-referencing
```

## Graph Queries

```python
client.execute(query: str, parameters: dict = None) -> List[Dict]
# Execute raw Cypher query
```

```python
client.get_graph_summary() -> Dict[str, Any]
# Returns: {entity_count, relationship_count, entities_by_type, relationships_by_type}
```

## Merge Entities

Merge duplicate entities into a single canonical entity. Not yet implemented as a single method — use these Cypher patterns:

### Step 1: Identify duplicates

```cypher
-- By similar names
MATCH (a:Person), (b:Person)
WHERE a.name < b.name
  AND (a.canonical_name = b.canonical_name OR a.name CONTAINS b.name)
RETURN a.name, b.name, a.mention_count, b.mention_count

-- By alias overlap
MATCH (a), (b)
WHERE a <> b AND any(alias IN a.aliases WHERE alias IN b.aliases)
RETURN a.name, b.name
```

### Step 2: Move relationships

```cypher
-- Move all outgoing relationships from secondary to canonical
MATCH (secondary)-[r]->(target)
WHERE secondary.name = $secondary_name
MERGE (canonical)-[r2:SAME_TYPE_AS_R]->(target)
SET r2 = properties(r)
DELETE r

-- Move all incoming relationships
MATCH (source)-[r]->(secondary)
WHERE secondary.name = $secondary_name
MERGE (source)-[r2:SAME_TYPE_AS_R]->(canonical)
SET r2 = properties(r)
DELETE r
```

### Step 3: Merge properties

```cypher
MATCH (canonical {name: $canonical_name}), (secondary {name: $secondary_name})
SET canonical.mention_count = canonical.mention_count + secondary.mention_count,
    canonical.aliases = canonical.aliases + secondary.aliases + [secondary.name],
    canonical.first_seen = CASE WHEN secondary.first_seen < canonical.first_seen
                           THEN secondary.first_seen ELSE canonical.first_seen END,
    canonical.last_seen = CASE WHEN secondary.last_seen > canonical.last_seen
                          THEN secondary.last_seen ELSE canonical.last_seen END,
    canonical.description = CASE WHEN size(secondary.description) > size(canonical.description)
                            THEN secondary.description ELSE canonical.description END
DELETE secondary
```

## KnowledgeGraphAgent

Higher-level agent that extracts entities and relationships from conversations.

```python
from qq.services.graph import KnowledgeGraphAgent

graph_agent = KnowledgeGraphAgent(model=model)

# Process conversation messages
result = graph_agent.process_messages(messages, file_sources, session_id, agent_id)
# result: {entities_created, relationships_created, ...}

# Get entity context for RAG
context = graph_agent.get_entity_context("John", depth=2)

# Link orphan entities (auto-discover relationships)
report = graph_agent.link_orphan_entities()

# Get summary
summary = graph_agent.get_graph_summary()
```

Sub-agents: `EntityAgent`, `RelationshipAgent`, `NormalizationAgent`, `GraphLinkingAgent`.

## Common Cypher Queries

### Counts

```cypher
-- Total entities
MATCH (n) WHERE NOT n:Source RETURN count(n) as total

-- Entities by type
MATCH (n) WHERE NOT n:Source
RETURN labels(n)[0] as type, count(n) as count ORDER BY count DESC

-- Total relationships
MATCH ()-[r]->() WHERE NOT type(r) IN ['EXTRACTED_FROM', 'EVIDENCES']
RETURN count(r) as total

-- Relationships by type
MATCH ()-[r]->() WHERE NOT type(r) IN ['EXTRACTED_FROM', 'EVIDENCES']
RETURN type(r) as type, count(r) as count ORDER BY count DESC
```

### Exploration

```cypher
-- Orphan entities (no relationships)
MATCH (n) WHERE NOT n:Source AND NOT (n)--() RETURN n.name, labels(n)[0] as type

-- Most connected entities
MATCH (n)-[r]-() WHERE NOT n:Source
RETURN n.name, labels(n)[0] as type, count(r) as connections
ORDER BY connections DESC LIMIT 10

-- Entity neighborhood
MATCH path = (n {name: $name})-[*1..2]-()
RETURN path

-- Recently mentioned entities
MATCH (n) WHERE NOT n:Source
RETURN n.name, n.last_seen, n.mention_count
ORDER BY n.last_seen DESC LIMIT 20
```

### Provenance

```cypher
-- Entities from a specific file
MATCH (n)-[:EXTRACTED_FROM]->(s:Source {file_path: $path})
RETURN n.name, labels(n)[0] as type

-- Sources for an entity
MATCH (n {name: $name})-[:EXTRACTED_FROM]->(s:Source)
RETURN s.source_type, s.file_path, s.session_id
```

### CLI Access

```bash
docker exec -it qq-neo4j cypher-shell -u neo4j -p refinerypass \
  "MATCH (n) RETURN count(n)"
```
