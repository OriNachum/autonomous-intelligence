Analyze the following conversation messages and extract key information to update memory notes.

**IMPORTANT:** Messages with role FILE_CONTENT contain actual file contents that were read. These are a PRIMARY source of information - extract facts, entities, configuration details, code patterns, and any other useful knowledge from file content.

The current notes contain these sections:
- Key Topics: Main subjects discussed
- Important Facts: Specific facts, data, or decisions
- People & Entities: Names, projects, systems mentioned
- Ongoing Threads: Unfinished discussions or pending items
- File Knowledge: Key information extracted from files read

Current notes content:
{current_notes}

Recent conversation (includes USER, ASSISTANT, and FILE_CONTENT messages):
{messages}

Based on the conversation, provide a JSON response with:
1. "additions": List of items to ADD to notes (not already present)
2. "removals": List of items to REMOVE (no longer relevant or resolved)
3. "summary": A brief 1-2 sentence summary of the key new information

**IMPORTANCE CLASSIFICATION:**
For each addition, classify its importance:
- "core": User identity, preferences, name, location, role, their projects - MOST IMPORTANT, never forget
- "high": Specific decisions, important facts, key relationships, hardware/setup
- "medium": Research topics, ongoing investigations, technical details
- "low": Temporary observations, single-mention facts, generic info

**DEDUPLICATION:**
Before adding, check if a similar item already exists. If so, skip it or suggest a removal.
Prefer specific, concrete facts over vague observations.

Each addition should have "section", "item", and "importance" fields.
Only include genuinely new information. Do not duplicate existing notes.
If nothing significant to add, return empty lists.

Response format:
{{
  "thinking": "F1: ...; F2: ... > C1; ...",
  "additions": [
    {{"section": "Key Topics", "item": "...", "importance": "medium"}},
    {{"section": "People & Entities", "item": "User's name is Ori", "importance": "core"}}
  ],
  "removals": ["pattern to remove"],
  "summary": "..."
}}

The "thinking" field captures your deductive reasoning chain. Use compact notation:
- `F1: [observation]` for facts
- `>` for inference
- `...` for intuitive leaps
- `;` to end chains

Respond with ONLY valid JSON, no other text.
