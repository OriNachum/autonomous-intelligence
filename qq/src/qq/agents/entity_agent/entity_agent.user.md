Analyze the following conversation and extract entities.
Entities can be of types: Person, Concept, Topic, Location, Event, Project, Software, Organization, File, Function, Class, Configuration.

**IMPORTANT:** Messages with role FILE_CONTENT contain actual file contents that were read. These are a PRIMARY source of entities - extract classes, functions, configuration keys, project names, dependencies, and any other named entities from file content.

Conversation (includes USER, ASSISTANT, and FILE_CONTENT messages):
{messages}

Respond with ONLY valid JSON in this format:
{{
  "entities": [
    {{"name": "Entity Name", "type": "Person", "description": "Brief description based on context"}}
  ]
}}
