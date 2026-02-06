# Plan: Neo4j Relationship Enhancement

**Goal**: Extract more relationships, add LLM-based normalization, enrich entity/relationship properties with generic fields (notes), and link orphan entities.

## Overview

| Component | Action |
|-----------|--------|
| Relationship extraction | Remove conservative filter, add more types, extract implicit relationships |
| Entity normalization | New LLM agent to normalize names and detect duplicates |
| Properties | Add `notes`, `confidence`, `evidence`, `aliases` fields |
| Orphan linking | New agent to find relationships for disconnected entities |
| Bug fix | Fix unlabeled node creation in `create_relationship` |

---

## Phase 1: Enhanced Relationship Extraction

### 1.1 Remove Conservative Filter
**File**: `src/qq/agents/relationship_agent/relationship_agent.user.md`

**Change line 39** from:
```
Only extract genuinely significant relationships. If nothing significant, return empty list.
```
**To**:
```
Extract ALL relationships you can identify, including:
- Explicit relationships stated directly
- Implicit relationships inferred from context
- Weak relationships (mentions, references, associations)
- Temporal relationships (precedes, follows)

Err on the side of extraction. Include uncertain relationships with lower confidence scores.
```

### 1.2 Add Relationship Types
**File**: `src/qq/agents/relationship_agent/relationship_agent.user.md`

Add after existing types (line 26):
```markdown
# Additional relationship types for comprehensive extraction:
- MENTIONS: Entity mentions another in context
- REFERENCES: Indirect reference to entity
- INFLUENCES: Entity influences another
- SIMILAR_TO: Entities share characteristics
- CONTRASTS_WITH: Opposing characteristics
- PRECEDES: Temporal ordering (before)
- FOLLOWS: Temporal ordering (after)
- ASSOCIATED_WITH: Loose association
- CO_OCCURS: Entities appear together
```

### 1.3 Enhance Relationship Output Format
**File**: `src/qq/agents/relationship_agent/relationship_agent.user.md`

Update JSON format (around line 28-33):
```markdown
{{
  "relationships": [
    {{
      "source": "Source Entity Name",
      "target": "Target Entity Name",
      "type": "RELATES_TO",
      "description": "Brief description",
      "notes": "Additional context or observations",
      "confidence": 0.85,
      "evidence": "Quote from conversation supporting this"
    }}
  ]
}}
```

---

## Phase 2: Enhanced Entity Extraction

### 2.1 Add Entity Fields
**File**: `src/qq/agents/entity_agent/entity_agent.user.md`

Update JSON format (around line 10-14):
```markdown
{{
  "entities": [
    {{
      "name": "Entity Name",
      "type": "Person",
      "description": "Brief description",
      "notes": "Additional observations or metadata",
      "confidence": 0.9
    }}
  ]
}}
```

---

## Phase 3: Normalization Agent (New)

### 3.1 Create Agent Structure
```
src/qq/agents/normalization_agent/
├── normalization_agent.py
├── normalization_agent.system.md
└── normalization_agent.user.md
```

### 3.2 normalization_agent.system.md
```markdown
You are an entity name normalization expert.
You standardize entity names and detect duplicates in knowledge graphs.
Use consistent capitalization, expand abbreviations, and identify aliases.

Respond in JSON starting with {
```

### 3.3 normalization_agent.user.md
```markdown
Normalize these newly extracted entities for consistency.

New entities:
{new_entities}

Existing graph entities:
{existing_entities}

For each new entity determine:
1. **canonical_name**: Proper, consistent form
2. **aliases**: Alternative names that map to this entity
3. **potential_duplicate**: Existing entity this might duplicate (or null)
4. **merge_confidence**: If duplicate, confidence 0.0-1.0

Rules:
- Use proper case for names
- Expand abbreviations (Dr., Prof.)
- Detect nickname/formal pairs (Mike -> Michael)
- Bind multi-word names

Respond with JSON:
{{
  "normalized": [
    {{
      "original_name": "...",
      "canonical_name": "...",
      "aliases": ["..."],
      "type": "...",
      "description": "...",
      "notes": "...",
      "potential_duplicate": "..." or null,
      "merge_confidence": 0.0-1.0
    }}
  ]
}}
```

### 3.4 normalization_agent.py
```python
class NormalizationAgent:
    def __init__(self, model: Any):
        self.model = model

    def normalize(self, entities: List[Dict], existing_entities: List[Dict]) -> List[Dict]:
        """Normalize entity names via LLM."""
        # Load prompts, call LLM, parse response
        # Return normalized entities with canonical_name, aliases, potential_duplicate
```

---

## Phase 4: Graph Linking Agent (New)

### 4.1 Create Agent Structure
```
src/qq/agents/graph_linking_agent/
├── graph_linking_agent.py
├── graph_linking_agent.system.md
└── graph_linking_agent.user.md
```

### 4.2 graph_linking_agent.system.md
```markdown
You find missing relationships between entities in knowledge graphs.
Be aggressive in finding connections - even weak associations are valuable.

Respond in JSON starting with {
```

### 4.3 graph_linking_agent.user.md
```markdown
These entities have NO relationships (orphans):
{orphan_entities}

These entities are connected:
{connected_entities}

For each orphan, find ANY possible relationships. Consider:
- Semantic similarity
- Implicit connections (same project/person/topic)
- Hierarchical (part-of, contains)
- Associative (co-mentioned, related topics)

Respond with JSON:
{{
  "suggested_relationships": [
    {{
      "source": "...",
      "target": "...",
      "type": "ASSOCIATED_WITH",
      "description": "...",
      "confidence": 0.6
    }}
  ]
}}
```

### 4.4 graph_linking_agent.py
```python
class GraphLinkingAgent:
    def __init__(self, model: Any, neo4j_client: Neo4jClient):
        self.model = model
        self.neo4j = neo4j_client

    def get_orphan_entities(self) -> List[Dict]:
        """Get entities with no relationships."""
        query = "MATCH (n) WHERE NOT (n)-[]-() RETURN n.name, labels(n)[0], n.description"
        return self.neo4j.execute(query)

    def link_orphans(self) -> Dict[str, Any]:
        """Find and create links for orphan entities."""
```

---

## Phase 5: Neo4j Client Updates

### 5.1 Fix Unlabeled Node Bug
**File**: `src/qq/knowledge/neo4j_client.py`

**Change `create_relationship` (lines 127-130)** from:
```python
query = f"""
    MERGE (a {{name: $source}})
    MERGE (b {{name: $target}})
    MERGE (a)-[r:{relationship_type}]->(b)
```
**To**:
```python
query = f"""
    MATCH (a {{name: $source}})
    MATCH (b {{name: $target}})
    MERGE (a)-[r:{relationship_type}]->(b)
```

This prevents creating unlabeled nodes when entities don't exist.

### 5.2 Enhanced Entity Properties
**File**: `src/qq/knowledge/neo4j_client.py`

Update `create_entity` to handle new properties:
- `notes` (string)
- `canonical_name` (string)
- `aliases` (list)
- `confidence` (float)
- `mention_count` (incremented on update)
- `first_seen` / `last_seen` timestamps

### 5.3 Enhanced Relationship Properties
**File**: `src/qq/knowledge/neo4j_client.py`

Update `create_relationship` to store:
- `notes` (string)
- `confidence` (float)
- `evidence` (string)
- `first_seen` / `last_seen` timestamps

---

## Phase 6: Graph Agent Integration

### 6.1 Update KnowledgeGraphAgent
**File**: `src/qq/services/graph.py`

Add imports and initialization:
```python
from qq.agents.normalization_agent.normalization_agent import NormalizationAgent
from qq.agents.graph_linking_agent.graph_linking_agent import GraphLinkingAgent

class KnowledgeGraphAgent:
    def __init__(self, ...):
        ...
        self.normalization_agent = NormalizationAgent(model)
        self.graph_linking_agent = None  # Lazy init
```

### 6.2 Update process_messages
**File**: `src/qq/services/graph.py` (lines 82-117)

New flow:
```python
def process_messages(self, messages):
    # 1. Extract entities
    entities = self.entity_agent.extract(messages)

    # 2. Extract relationships (now more aggressive)
    relationships = self.relationship_agent.extract(messages, entities)

    # 3. Normalize entities (NEW)
    existing = self._get_existing_entity_names()
    normalized = self.normalization_agent.normalize(entities, existing)

    # 4. Store with enhanced properties
    self._store_extraction({"entities": normalized, "relationships": relationships})

    return result
```

### 6.3 Update _store_extraction
**File**: `src/qq/services/graph.py` (lines 119-176)

Pass new fields to Neo4j:
```python
self.neo4j.create_entity(
    entity_type=entity.get("type"),
    name=entity.get("canonical_name") or entity.get("name"),
    properties={
        "description": entity.get("description", ""),
        "notes": entity.get("notes", ""),
        "confidence": entity.get("confidence", 1.0),
    },
    aliases=entity.get("aliases", []),
    canonical_name=entity.get("canonical_name"),
    embedding=embedding,
)

self.neo4j.create_relationship(
    source_name=rel.get("source"),
    target_name=rel.get("target"),
    relationship_type=rel.get("type"),
    properties={
        "description": rel.get("description", ""),
        "notes": rel.get("notes", ""),
        "confidence": rel.get("confidence", 1.0),
        "evidence": rel.get("evidence", ""),
    },
)
```

### 6.4 Add Periodic Orphan Linking
**File**: `src/qq/services/graph.py`

```python
def link_orphan_entities(self):
    """Run graph linking agent to connect orphan entities."""
    if not self.graph_linking_agent:
        self.graph_linking_agent = GraphLinkingAgent(self.model, self.neo4j)

    result = self.graph_linking_agent.link_orphans()
    # Store suggested relationships
    for rel in result.get("suggested_relationships", []):
        self.neo4j.create_relationship(...)
```

---

## Implementation Order

1. **Phase 1**: Prompt changes (quick wins - more relationships immediately)
2. **Phase 5.1**: Fix unlabeled node bug (prevent new orphans)
3. **Phase 2**: Entity prompt enhancement
4. **Phase 5.2-5.3**: Neo4j property updates
5. **Phase 6.3**: Storage integration
6. **Phase 3**: Normalization agent
7. **Phase 6.2**: Integration
8. **Phase 4**: Graph linking agent
9. **Phase 6.4**: Periodic linking

---

## Verification

1. Run extraction on test conversation
2. Check Neo4j: `MATCH (n) RETURN count(n), count{ MATCH ()-[r]->() RETURN r }`
3. Verify no new unlabeled nodes: `MATCH (n) WHERE size(labels(n))=0 RETURN count(n)`
4. Check orphan reduction: `MATCH (n) WHERE NOT (n)--() RETURN count(n)`
5. Verify new properties: `MATCH (n) RETURN n.notes, n.confidence LIMIT 5`

---

## Files to Modify

| File | Changes |
|------|---------|
| `src/qq/agents/relationship_agent/relationship_agent.user.md` | Remove filter, add types, enhance format |
| `src/qq/agents/entity_agent/entity_agent.user.md` | Add notes, confidence fields |
| `src/qq/knowledge/neo4j_client.py` | Fix MERGE bug, add property support |
| `src/qq/services/graph.py` | Integrate normalization, linking, enhanced storage |

## Files to Create

| File | Purpose |
|------|---------|
| `src/qq/agents/normalization_agent/normalization_agent.py` | LLM-based name normalization |
| `src/qq/agents/normalization_agent/normalization_agent.system.md` | System prompt |
| `src/qq/agents/normalization_agent/normalization_agent.user.md` | User prompt template |
| `src/qq/agents/graph_linking_agent/graph_linking_agent.py` | Orphan relationship finder |
| `src/qq/agents/graph_linking_agent/graph_linking_agent.system.md` | System prompt |
| `src/qq/agents/graph_linking_agent/graph_linking_agent.user.md` | User prompt template |
