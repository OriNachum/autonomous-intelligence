# Investigation: Neo4j Entity-Relationship Imbalance

**Date:** 2026-02-05
**Status:** Investigation Complete
**Finding:** Multiple root causes identified - both by design and bugs

## Summary

Investigation into why the Neo4j knowledge graph has more entities than relationships. The ratio is approximately 1.08 relationships per entity, with **64 out of 143 entities (45%) having zero relationships**.

## Current State

```
Total entities:      143
Total relationships: 155
Ratio:              1.08 relationships per entity
Orphan entities:     64 (45% with no relationships)
Unlabeled nodes:     52 (created by relationship MERGE bug)
```

### Entity Distribution by Type
| Type | Count |
|------|-------|
| Concept | 57 |
| Person | 15 |
| File | 14 |
| Project | 13 |
| Software | 13 |
| Location | 8 |
| Topic | 6 |
| Function | 5 |
| Organization | 4 |
| Configuration | 3 |
| Event | 2 |
| Other | 3 |

### Relationship Distribution per Entity
| Relationships | Entity Count |
|---------------|-------------|
| 0 | 64 |
| 1 | 59 |
| 2 | 35 |
| 3+ | 31 |

## Root Causes Identified

### 1. BUG: Unlabeled Node Creation (52 nodes)

**Severity:** High
**Location:** `src/qq/knowledge/neo4j_client.py:127-130`

The `create_relationship` method uses MERGE without labels:

```cypher
MERGE (a {name: $source})
MERGE (b {name: $target})
MERGE (a)-[r:RELATIONSHIP_TYPE]->(b)
```

When the relationship agent references an entity name that differs slightly from what the entity agent extracted (e.g., "Mike's Daily Paper" vs "Mike Paper Review"), Neo4j creates a new **unlabeled** node instead of finding the existing labeled one.

**Evidence:**
- 52 entities have no labels (`size(labels(n)) = 0`)
- These unlabeled nodes have relationships (created by MERGE)
- They lack descriptions (not created by entity_agent)

**Examples of unlabeled nodes created:**
- `Review_2024_12_04.md` (4 out, 3 in)
- `KAN` (4 out, 1 in)
- `Kolmogorov–Arnold theorem` (0 out, 4 in)
- `FILE_CONTENT`, `USER`, `ASSISTANT` (erroneous extractions)

### 2. DESIGN: Strict Relationship Filtering

**Severity:** By Design
**Location:** `src/qq/agents/relationship_agent/relationship_agent.user.md:39`

The relationship agent prompt explicitly states:
> "Only extract genuinely significant relationships. If nothing significant, return empty list."

This conservative approach intentionally filters out:
- Weak or implicit relationships
- Trivial mentions
- Tangential connections

This is a deliberate quality-over-quantity trade-off.

### 3. BUG: Entity Name Inconsistency

**Severity:** Medium
**Location:** Entity extraction LLM behavior

The same concept is extracted with different names across conversations:

**"Mike" Variants (11 different representations):**
- `Mike` (Person) - 18 connections
- `Mike Erlihson` (Person) - 11 connections
- `Mike's Daily Paper` (Concept) - 6 connections
- `Mike's Daily Paper` (Topic) - 2 connections
- `Mike's Daily Paper` (Project) - 2 connections
- `Mike Paper Review` (Concept) - 2 connections
- Plus 5 path-based location variants

These should be **1 entity with 1 canonical name**, not 11 separate entities.

### 4. DESIGN: Limited Context Window

**Severity:** By Design
**Location:** `src/qq/agents/entity_agent/entity_agent.py:66-68`

Both agents only process the **last 20 messages**:
```python
recent_messages = messages[-20:]
```

Entities mentioned earlier in conversation are not connected to entities mentioned later, creating orphan clusters.

### 5. BUG: Cross-Session Entity Fragmentation

**Severity:** Medium

Each conversation session extracts entities independently. An entity like "QQ" might be extracted in:
- Session 1: With relationships to "Memory", "Skills"
- Session 2: With relationships to "Neo4j", "MongoDB"

But there's no mechanism to link Session 1's "QQ" relationships with Session 2's extractions.

## Recommendations

### Immediate Fixes

#### Fix 1: Add Labels to Relationship MERGE

**File:** `src/qq/knowledge/neo4j_client.py`

Change `create_relationship` to use existing labels:

```python
def create_relationship(
    self,
    source_name: str,
    target_name: str,
    relationship_type: str,
    properties: Optional[Dict[str, Any]] = None,
) -> bool:
    # First, check if entities exist and get their labels
    check_query = """
        OPTIONAL MATCH (a {name: $source})
        OPTIONAL MATCH (b {name: $target})
        RETURN labels(a) as source_labels, labels(b) as target_labels
    """
    result = self.execute(check_query, {"source": source_name, "target": target_name})

    if not result:
        return False

    source_labels = result[0].get("source_labels")
    target_labels = result[0].get("target_labels")

    # Only create relationship if BOTH entities already exist with labels
    if not source_labels or not target_labels:
        logger.warning(f"Skipping relationship {source_name}->{target_name}: entities not found")
        return False

    # Use labels in MATCH for precise node matching
    source_label = source_labels[0]
    target_label = target_labels[0]

    query = f"""
        MATCH (a:{source_label} {{name: $source}})
        MATCH (b:{target_label} {{name: $target}})
        MERGE (a)-[r:{relationship_type}]->(b)
        RETURN type(r) as rel_type
    """
    # ... rest of method
```

#### Fix 2: Entity Name Normalization

Add a normalization layer before creating entities:

```python
def normalize_entity_name(name: str) -> str:
    """Normalize entity names for consistency."""
    # Remove possessive forms
    name = re.sub(r"'s\b", "", name)
    # Normalize whitespace
    name = " ".join(name.split())
    # Title case for consistency
    return name.strip()
```

#### Fix 3: Delete Orphan Unlabeled Nodes

Cleanup query to run periodically:

```cypher
MATCH (n)
WHERE size(labels(n)) = 0 AND NOT (n)--()
DELETE n
```

### Medium-Term Improvements

#### Entity Deduplication Agent

Create a new agent that runs periodically to:
1. Find entities with similar names (fuzzy matching)
2. Merge duplicate entities
3. Redirect relationships to canonical entity

#### Relationship Inference Agent

Create an agent that:
1. Analyzes orphan entities
2. Searches conversation history for implicit relationships
3. Suggests new relationships for human review

#### Graph Density Monitoring

Add metrics to track:
- Ratio of relationships to entities
- Orphan entity count
- Unlabeled node count
- Entity type distribution

## Skills Created

As part of this investigation, two new skills were created:

### neo4j-query
**Location:** `.agent/skills/neo4j-query/SKILL.md`
**Triggers:** neo4j, knowledge graph, entities, relationships, graph query, cypher

Provides Python and CLI examples for querying Neo4j knowledge graph.

### mongodb-query
**Location:** `.agent/skills/mongodb-query/SKILL.md`
**Triggers:** mongodb, mongo, notes store, memory storage, notes query

Provides Python and CLI examples for querying MongoDB notes store.

## Appendix: Key Queries Used

### Find Orphan Entities
```cypher
MATCH (n) WHERE NOT (n)--()
RETURN n.name, labels(n)[0] as type
```

### Find Unlabeled Nodes
```cypher
MATCH (n) WHERE size(labels(n)) = 0
RETURN n.name, count(*) as cnt
```

### Relationship Distribution
```cypher
MATCH (n)
OPTIONAL MATCH (n)-[r]-()
WITH n, count(r) as rel_count
RETURN rel_count, count(n) as entities_with_count
ORDER BY rel_count
```

### Most Connected Entities
```cypher
MATCH (n)-[r]-()
RETURN n.name, labels(n)[0] as type, count(r) as connections
ORDER BY connections DESC
LIMIT 15
```

### Graph Summary
```cypher
-- Entities by type
MATCH (n) RETURN labels(n)[0] as type, count(n) as count ORDER BY count DESC

-- Relationships by type
MATCH ()-[r]->() RETURN type(r) as type, count(r) as count ORDER BY count DESC
```

## Conclusion

The entity-relationship imbalance stems from **both bugs and design decisions**:

| Cause | Type | Impact | Fix Priority |
|-------|------|--------|--------------|
| Unlabeled MERGE nodes | Bug | 52 orphan nodes | High |
| Entity name inconsistency | Bug | 11+ duplicate clusters | High |
| Strict relationship filtering | Design | By intention | None |
| 20-message context limit | Design | Cluster fragmentation | Medium |
| Cross-session fragmentation | Design | No entity linking | Low |

The most impactful immediate fix is preventing unlabeled node creation by requiring entities to exist before creating relationships between them.
