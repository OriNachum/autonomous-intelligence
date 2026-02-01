Analyze the following conversation and the provided list of entities. Identify relationships between these entities based on the conversation.

Conversation:
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

Respond with ONLY valid JSON in this format:
{{
  "relationships": [
    {{"source": "Source Entity Name", "target": "Target Entity Name", "type": "RELATES_TO", "description": "Brief description"}}
  ]
}}

Only extract genuinely significant relationships. If nothing significant, return empty list.
