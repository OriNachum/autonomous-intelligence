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

Respond with ONLY valid JSON in this format:
{{
  "relationships": [
    {{"source": "Source Entity Name", "target": "Target Entity Name", "type": "RELATES_TO", "description": "Brief description", "reasoning": "F1: ..., F2: ... > relationship type"}}
  ]
}}

The "reasoning" field is optional but recommended for ambiguous cases. Use compact notation:
- `F1: [observation]` for facts
- `>` for inference (e.g., `F1: import present, F2: runtime call > USES not DEPENDS_ON`)

Only extract genuinely significant relationships. If nothing significant, return empty list.
