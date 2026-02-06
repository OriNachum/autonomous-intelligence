# Plan: Remove Guided Thinking

## Problem

The system prompts include a custom "structured thinking" notation (`F1:`, `F2:`, `>`, `...`, `;`) that was designed to guide model reasoning. Modern models (especially those with extended thinking / chain-of-thought) already reason internally before responding. The guided thinking notation:

1. **Confuses the model** — it tries to reconcile its own reasoning with the imposed notation, producing worse outputs
2. **Wastes tokens** — the "thinking" field in JSON responses adds output overhead with no benefit
3. **Adds complexity** — six different Python files strip `<think>` tags, and prompts carry notation documentation

## Scope of Changes

### 1. Default Agent System Prompt

**File:** `src/qq/agents/default/default.system.md`

**Remove lines 22-55** — the entire "Structured Thinking" section:
- Notation definitions (`F1:`, `F2:`, `>`, `...`, `;`)
- Format template (Observations / Reasoning / Answer)
- When to use / When NOT to use guidance

**Keep** line 19: "Explain your reasoning when solving complex problems" — this is a natural instruction, not a notation system.

### 2. Notes Agent System Prompt

**File:** `src/qq/agents/notes/notes.system.md`

**Remove lines 4-9** — the deductive notation section:
```
Your deductive notation:
- `F1, F2 > conclusion` — facts lead to conclusion
- `> ... >` — intuitive leap
- `;` — end of chain

Example: `F1: user said "I'm Alex", F2: repeated 3 times > core identity fact`
```

**Keep** lines 1-2 (Watson persona) and line 11-12 (general instruction). The Watson persona is fine — just remove the notation system.

### 3. Notes User Prompt

**File:** `src/qq/agents/notes/notes.user.md`

**Remove the "thinking" field** from the JSON response format (lines 40, 49-53):
- Remove `"thinking": "F1: ...; F2: ... > C1; ..."` from the example JSON
- Remove the notation explanation block (lines 49-53)

The model can reason internally; it doesn't need to output a thinking field.

### 4. Entity Agent User Prompt

**File:** `src/qq/agents/entity_agent/entity_agent.user.md`

**Remove the "reasoning" field** from the JSON format (line 18) and the notation explanation (lines 23-25):
```
"reasoning": "F1: ..., F2: ... > type choice"
```
```
The "reasoning" field is optional but recommended...
```

### 5. Entity Agent System Prompt

**File:** `src/qq/agents/entity_agent/entity_agent.system.md`

**Remove** the reasoning notation lines (likely lines 4-5):
```
For ambiguous cases, note your reasoning:
`F1: class keyword, F2: has methods > Class type`
```

### 6. Relationship Agent User Prompt

**File:** `src/qq/agents/relationship_agent/relationship_agent.user.md`

**Remove the "reasoning" field** from the JSON format (line 50) and the notation explanation (lines 55-57):
```
"reasoning": "F1: ..., F2: ... > relationship type"
```
```
The "reasoning" field is optional but recommended...
```

### 7. Relationship Agent System Prompt

**File:** `src/qq/agents/relationship_agent/relationship_agent.system.md`

**Remove** the reasoning notation lines (likely lines 4-5):
```
For ambiguous relationship types, note your reasoning:
`F1: import present, F2: called in method > USES (not DEPENDS_ON)`
```

### 8. Graph Linking Agent User Prompt

**File:** `src/qq/agents/graph_linking_agent/graph_linking_agent.user.md`

The `"reasoning"` field here (line 24) is a natural-language "Why these entities should be connected" — **no notation to remove**, but review whether to keep/simplify.

### 9. Python: `<think>` Tag Stripping (Keep but Simplify)

These files strip `<think>...</think>` tags from model output. **Keep this logic** — some models still emit thinking tags regardless of prompts. But it's worth noting these exist for future cleanup if switching to models that never emit them.

| File | Method |
|------|--------|
| `src/qq/agents/notes/notes.py` | `parse_json_response()` — regex strip |
| `src/qq/agents/entity_agent/entity_agent.py` | `_clean_json_response()` — split on `</think>` |
| `src/qq/agents/relationship_agent/relationship_agent.py` | `_clean_json_response()` |
| `src/qq/agents/normalization_agent/normalization_agent.py` | `_clean_json_response()` |
| `src/qq/agents/graph_linking_agent/graph_linking_agent.py` | `_clean_json_response()` |
| `src/qq/services/alignment.py` | `_parse_json_response()` — regex strip |
| `src/qq/memory/notes_agent.py` | `_extract_json()` — multi-strategy |

### 10. Python: Remove "thinking" Key Handling

**File:** `src/qq/memory/notes_agent.py` and `src/qq/agents/notes/notes.py`

If these files reference or process the `"thinking"` key from JSON responses, remove that handling since the field will no longer be in the output format.

## Execution Order

1. **Prompts first** — edit all `.system.md` and `.user.md` files (steps 1-8)
2. **Python second** — remove "thinking" key handling (step 10)
3. **Keep** `<think>` tag stripping (step 9) — defensive, low cost
4. **Test** — run `uv run pytest` to verify nothing breaks
5. **Manual test** — run a conversation to verify clean model output

## Risk Assessment

- **Low risk** — these are prompt-only changes (mostly), not logic changes
- **The "thinking" field removal** in notes could affect parsing if the model still outputs it — the JSON parsers should handle extra keys gracefully, but verify
- **`<think>` stripping stays** as defensive code, so no risk from models that still emit thinking tags
