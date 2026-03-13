# Knowledge Graph Indexing (Neo4j)

Structured entities and relationships are stored in Neo4j, forming a queryable knowledge graph with embeddings for semantic search.

## Entity Node Schema

Created via `neo4j_client.py:62-123`:

```cypher
(n:EntityType {
  name: "identifier string",
  canonical_name: "normalized form",
  aliases: ["alias1", "alias2"],
  description: "what this entity is",
  embedding: [float, ...],
  confidence: 0.85,
  mention_count: 1,
  first_seen: datetime,
  last_seen: datetime,
  source_first_id: "original source",
  source_latest_id: "most recent source"
})
```

Entity types: `Person`, `Concept`, `Topic`, `Location`, `Event`

MERGE logic:
- **ON CREATE**: Set `mention_count=1`, `first_seen`, `last_seen`, `source_first_id`
- **ON MATCH**: Increment `mention_count`, update `last_seen`, `source_latest_id`

## Relationship Schema

Created via `neo4j_client.py:125-177`:

```cypher
(source)-[r:RELATIONSHIP_TYPE {
  description: "string",
  notes: "string",
  confidence: 0.85,
  evidence: "supporting text",
  mention_count: 1,
  first_seen: datetime,
  last_seen: datetime
}]->(target)
```

Types: `RELATES_TO`, `KNOWS`, `WORKS_ON`, `OWNS`, `CREATED`, etc. (22 total, upper-cased with underscores).

## Extraction Pipeline

Orchestrated by `KnowledgeGraphAgent` (`src/qq/services/graph.py:105-160`):

### 1. Entity Extraction (`entity_agent.py:43-98`)
- Formats last 20 messages
- LLM returns JSON: `{"entities": [{"name", "type", "description", "aliases", "confidence"}]}`
- Cleans response (removes thinking tags, markdown fences)

### 2. Relationship Extraction (`relationship_agent.py:43-107`)
- Takes messages + extracted entities as input
- LLM returns: `{"relationships": [{"source", "target", "type", "description", "evidence", "confidence"}]}`

### 3. Normalization (`normalization_agent.py:44-125`)
- Detects duplicate/variant entity names
- Adds `canonical_name`, `aliases`, `potential_duplicate`, `merge_confidence`
- Merges normalized fields back into original entities

### 4. Storage (`graph.py:162-296`)
1. Create Source nodes for file sources + conversation sources
2. For each entity: create node, generate embedding, link to Source via `EXTRACTED_FROM`
3. For each relationship: create edge, link evidence to Source via `EVIDENCES`

### 5. Graph Linking (`graph_linking_agent/`)
- Post-processing step to connect orphan entities
- Identifies missing relationships between existing entities

## Search & Query

### Embedding Similarity Search (`neo4j_client.py:354-409`)
- `search_entities_by_embedding()`: Cosine similarity on entity embeddings
- Fetches all entities with embeddings, scores against query embedding
- Returns top-k sorted by similarity
- Optional `entity_type` filter

### Relationship Traversal (`neo4j_client.py:411-439`)
- `get_related_entities()`: Variable-depth path traversal
- `MATCH path = (start)-[*1..depth]-(related)`
- Returns related entities ordered by path distance

### Graph Summary (`neo4j_client.py:462-481`)
- Counts entities by type
- Counts relationships by type
- Used by the retrieval agent for context summary

## Access Tracking

`increment_mention_count()` (`neo4j_client.py:441-460`):
- +1 each time an entity is re-encountered in conversation
- Updates `last_seen` timestamp
- Serves as an implicit importance signal
