Analyze the following conversation and the provided list of entities. Identify relationships between these entities based on the conversation.

**IMPORTANT:** Messages with role FILE_CONTENT contain actual file contents that were read. These are a PRIMARY source of relationships - extract imports, inheritance, function calls, configuration dependencies, and any structural relationships from file content.

Conversation (includes USER, ASSISTANT, and FILE_CONTENT messages):
{messages}

Entities found:
{entities}

Relationship types:
- KNOWS: Person knows Person
- RELATES_TO: General relationship
- USES: Person uses Concept/Tool
- PART_OF: Concept is part of Concept
- CAUSES: Event causes Event/State
- WORKS_ON: Person works on Topic/Project
- LOCATED_IN: Entity located in Location
- DEFINED_AS: Concept is defined as description
- IMPORTS: File/Module imports another
- EXTENDS: Class extends another Class
- IMPLEMENTS: Class implements Interface
- CALLS: Function calls another Function
- DEPENDS_ON: Entity depends on another Entity
- CONFIGURES: Configuration key configures Entity
- CONTAINS: File/Module contains Function/Class

Additional relationship types for comprehensive extraction:
- MENTIONS: Entity mentions another in context
- REFERENCES: Indirect reference to entity
- INFLUENCES: Entity influences another
- SIMILAR_TO: Entities share characteristics
- CONTRASTS_WITH: Opposing characteristics
- PRECEDES: Temporal ordering (before)
- FOLLOWS: Temporal ordering (after)
- ASSOCIATED_WITH: Loose association
- CO_OCCURS: Entities appear together

Respond with ONLY valid JSON in this format:
{{
  "relationships": [
    {{
      "source": "Source Entity Name",
      "target": "Target Entity Name",
      "type": "RELATES_TO",
      "description": "Brief description",
      "notes": "Additional context or observations",
      "confidence": 0.85,
      "evidence": "Quote from conversation supporting this",
      "reasoning": "F1: ..., F2: ... > relationship type"
    }}
  ]
}}

The "reasoning" field is optional but recommended for ambiguous cases. Use compact notation:
- `F1: [observation]` for facts
- `>` for inference (e.g., `F1: import present, F2: runtime call > USES not DEPENDS_ON`)

Extract ALL relationships you can identify, including:
- Explicit relationships stated directly
- Implicit relationships inferred from context
- Weak relationships (mentions, references, associations)
- Temporal relationships (precedes, follows)

Err on the side of extraction. Include uncertain relationships with lower confidence scores.
