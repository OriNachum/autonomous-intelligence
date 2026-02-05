# Knowledge Graph (Neo4j)

The Knowledge Graph structures information into entities and their relationships, allowing the agent to understand complex connections between concepts, people, and topics.

## Overview

| Property | Value |
|----------|-------|
| **Agent** | `KnowledgeGraphAgent` |
| **Source** | `src/qq/services/graph.py` |
| **Storage** | Neo4j Graph Database |
| **Port** | 7474 (HTTP), 7687 (Bolt) |

## Extraction Pipeline

The knowledge graph extraction uses a multi-agent pipeline:

```
Conversation Messages
        │
        ▼
┌───────────────────┐
│   EntityAgent     │  Extract entities (Person, Concept, Topic, etc.)
└─────────┬─────────┘
          │
          ▼
┌───────────────────┐
│ RelationshipAgent │  Extract relationships between entities
└─────────┬─────────┘
          │
          ▼
┌───────────────────┐
│NormalizationAgent │  Normalize names, detect duplicates
└─────────┬─────────┘
          │
          ▼
┌───────────────────┐
│    Neo4j Store    │  Store with embeddings and metadata
└───────────────────┘
```

### Sub-Agents

| Agent | Source | Purpose |
|-------|--------|---------|
| `EntityAgent` | `src/qq/agents/entity_agent/` | Extracts entities from conversation |
| `RelationshipAgent` | `src/qq/agents/relationship_agent/` | Extracts relationships between entities |
| `NormalizationAgent` | `src/qq/agents/normalization_agent/` | Normalizes entity names, detects duplicates |
| `GraphLinkingAgent` | `src/qq/agents/graph_linking_agent/` | Finds relationships for orphan entities |

## Schema

### Nodes (Entities)

| Property | Type | Description |
|----------|------|-------------|
| `name` | string | Unique identifier (primary key) |
| `description` | string | Contextual description |
| `notes` | string | Additional observations or metadata |
| `confidence` | float | Extraction confidence (0.0-1.0) |
| `canonical_name` | string | Normalized/canonical form of the name |
| `aliases` | list | Alternative names for this entity |
| `embedding` | list[float] | Vector representation for similarity search |
| `mention_count` | int | Number of times entity was mentioned |
| `first_seen` | datetime | When entity was first created |
| `last_seen` | datetime | When entity was last updated |

**Entity Labels (Types)**:
- `Person` - People, users, collaborators
- `Concept` - Abstract concepts, ideas
- `Topic` - Discussion topics
- `Location` - Physical or virtual locations
- `Event` - Events, occurrences
- `Project` - Projects, initiatives
- `Software` - Software, tools, applications
- `Organization` - Companies, teams, groups
- `File` - Files, documents
- `Function` - Code functions
- `Class` - Code classes
- `Configuration` - Config keys, settings

### Edges (Relationships)

| Property | Type | Description |
|----------|------|-------------|
| `description` | string | Details about the relationship |
| `notes` | string | Additional context |
| `confidence` | float | Extraction confidence (0.0-1.0) |
| `evidence` | string | Quote from conversation supporting this |
| `mention_count` | int | Number of times relationship was mentioned |
| `first_seen` | datetime | When relationship was first created |
| `last_seen` | datetime | When relationship was last updated |

**Relationship Types**:

| Type | Description |
|------|-------------|
| `KNOWS` | Person knows Person |
| `RELATES_TO` | General relationship |
| `USES` | Person uses Concept/Tool |
| `PART_OF` | Concept is part of Concept |
| `CAUSES` | Event causes Event/State |
| `WORKS_ON` | Person works on Topic/Project |
| `LOCATED_IN` | Entity located in Location |
| `DEFINED_AS` | Concept is defined as description |
| `IMPORTS` | File/Module imports another |
| `EXTENDS` | Class extends another Class |
| `IMPLEMENTS` | Class implements Interface |
| `CALLS` | Function calls another Function |
| `DEPENDS_ON` | Entity depends on another Entity |
| `CONFIGURES` | Configuration key configures Entity |
| `CONTAINS` | File/Module contains Function/Class |
| `MENTIONS` | Entity mentions another in context |
| `REFERENCES` | Indirect reference to entity |
| `INFLUENCES` | Entity influences another |
| `SIMILAR_TO` | Entities share characteristics |
| `CONTRASTS_WITH` | Opposing characteristics |
| `PRECEDES` | Temporal ordering (before) |
| `FOLLOWS` | Temporal ordering (after) |
| `ASSOCIATED_WITH` | Loose association |
| `CO_OCCURS` | Entities appear together |

## Normalization

The `NormalizationAgent` ensures entity consistency:

1. **Canonical Names**: Standardizes entity names (proper case, expanded abbreviations)
2. **Alias Detection**: Identifies nickname/formal pairs (Mike -> Michael)
3. **Duplicate Detection**: Finds potential duplicates in existing graph
4. **Merge Confidence**: Provides confidence score for merge decisions

Example normalization:
```json
{
  "original_name": "Dr. Smith",
  "canonical_name": "Doctor Smith",
  "aliases": ["Dr. Smith", "Smith"],
  "potential_duplicate": "John Smith",
  "merge_confidence": 0.7
}
```

## Orphan Linking

The `GraphLinkingAgent` connects disconnected entities:

1. Queries for entities with no relationships (orphans)
2. Analyzes semantic similarity with connected entities
3. Suggests relationships based on:
   - Semantic similarity (similar names, topics, domains)
   - Implicit connections (same project/person/topic)
   - Hierarchical relationships (part-of, contains)
   - Associative patterns (co-mentioned, related topics)

Usage:
```python
graph_agent = KnowledgeGraphAgent(...)
result = graph_agent.link_orphan_entities()
# Returns: {"linked": 5, "suggested_relationships": [...]}
```

## Implementation

### Neo4jClient

Source: `src/qq/knowledge/neo4j_client.py`

Key methods:
- `create_entity()` - Create or update an entity node
- `create_relationship()` - Create a relationship (requires existing entities)
- `get_entity()` - Get entity by name
- `search_entities_by_embedding()` - Vector similarity search
- `get_related_entities()` - Get entities related up to N hops
- `get_graph_summary()` - Get entity/relationship counts

### Relationship Creation Safety

Relationships only connect existing entities (MATCH, not MERGE):
```cypher
MATCH (a {name: $source})
MATCH (b {name: $target})
MERGE (a)-[r:RELATIONSHIP_TYPE]->(b)
```

This prevents creating unlabeled "orphan" nodes when referenced entities don't exist.

## Querying

### Cypher Examples

Get entity with relationships:
```cypher
MATCH (n {name: "Python"})
OPTIONAL MATCH (n)-[r]-(related)
RETURN n, r, related
```

Find orphan entities:
```cypher
MATCH (n)
WHERE NOT (n)-[]-()
RETURN n.name, labels(n)[0], n.description
```

Get graph statistics:
```cypher
MATCH (n) RETURN labels(n)[0] as type, count(n) as count
UNION
MATCH ()-[r]->() RETURN type(r) as type, count(r) as count
```

## Verification Queries

After running extraction, verify results:

```cypher
-- Total nodes and relationships
MATCH (n) RETURN count(n) as nodes
MATCH ()-[r]->() RETURN count(r) as relationships

-- Check for unlabeled nodes (should be 0)
MATCH (n) WHERE size(labels(n))=0 RETURN count(n)

-- Orphan count
MATCH (n) WHERE NOT (n)--() RETURN count(n)

-- Check new properties
MATCH (n) RETURN n.name, n.notes, n.confidence LIMIT 5
```

## Related Documentation

- [Memory Overview](./memory.md)
- [Agents](./agents.md)
