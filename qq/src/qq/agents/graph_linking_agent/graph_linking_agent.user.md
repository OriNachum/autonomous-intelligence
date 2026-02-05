These entities have NO relationships (orphans):
{orphan_entities}

These entities are connected:
{connected_entities}

For each orphan, find ANY possible relationships. Consider:
- Semantic similarity (similar names, topics, domains)
- Implicit connections (same project/person/topic)
- Hierarchical (part-of, contains)
- Associative (co-mentioned, related topics)
- Type-based (entities of same type often relate)

Respond with JSON:
{{
  "suggested_relationships": [
    {{
      "source": "...",
      "target": "...",
      "type": "ASSOCIATED_WITH",
      "description": "Brief description of the relationship",
      "notes": "Additional context",
      "confidence": 0.6,
      "reasoning": "Why these entities should be connected"
    }}
  ]
}}

Relationship types to use:
- ASSOCIATED_WITH: General loose association
- SIMILAR_TO: Entities share characteristics
- PART_OF: Entity is part of another
- RELATED_TO: General relationship
- MENTIONS: One references/mentions another
- CO_OCCURS: Entities appear in similar contexts
