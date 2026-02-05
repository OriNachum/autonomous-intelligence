Analyze the following conversation and extract entities.
Entities can be of types: Person, Concept, Topic, Location, Event, Project, Software, Organization, File, Function, Class, Configuration.

**IMPORTANT:** Messages with role FILE_CONTENT contain actual file contents that were read. These are a PRIMARY source of entities - extract classes, functions, configuration keys, project names, dependencies, and any other named entities from file content.

Conversation (includes USER, ASSISTANT, and FILE_CONTENT messages):
{messages}

Respond with ONLY valid JSON in this format:
{{
  "entities": [
    {{"name": "Entity Name", "type": "Person", "description": "Brief description based on context", "reasoning": "F1: ..., F2: ... > type choice"}}
  ]
}}

The "reasoning" field is optional but recommended for ambiguous cases. Use compact notation:
- `F1: [observation]` for facts
- `>` for inference (e.g., `F1: class keyword, F2: has methods > Class type`)
