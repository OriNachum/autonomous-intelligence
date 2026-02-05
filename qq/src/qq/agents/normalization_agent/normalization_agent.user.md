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
      "confidence": 0.9,
      "potential_duplicate": "..." or null,
      "merge_confidence": 0.0-1.0
    }}
  ]
}}
