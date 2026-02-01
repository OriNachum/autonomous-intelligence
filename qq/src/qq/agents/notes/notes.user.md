Analyze the following conversation messages and extract key information to update memory notes.

The current notes contain these sections:
- Key Topics: Main subjects discussed
- Important Facts: Specific facts, data, or decisions
- People & Entities: Names, projects, systems mentioned
- Ongoing Threads: Unfinished discussions or pending items

Current notes content:
{current_notes}

Recent conversation:
{messages}

Based on the conversation, provide a JSON response with:
1. "additions": List of items to ADD to notes (not already present)
2. "removals": List of items to REMOVE (no longer relevant or resolved)
3. "summary": A brief 1-2 sentence summary of the key new information

Each addition should have "section" and "item" fields.
Only include genuinely new information. Do not duplicate existing notes.
If nothing significant to add, return empty lists.

Response format:
{{
  "additions": [
    {{"section": "Key Topics", "item": "..."}}
  ],
  "removals": ["pattern to remove"],
  "summary": "..."
}}

Respond with ONLY valid JSON, no other text.
