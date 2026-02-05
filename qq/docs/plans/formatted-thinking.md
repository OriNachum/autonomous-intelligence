# Formatted Thinking Strategy

## Executive Summary

Introduce a compact, structured reasoning format across all QQ agents that makes inference chains explicit and traceable using a notation system: facts, inference (`>`), and thought leaps (`...`).

---

## Current State

### Agents Overview

| Agent | Persona | Output Format | Thinking Style |
|-------|---------|---------------|----------------|
| **default** | "qq, entity of this machine" | Free-form markdown | Explains reasoning in prose |
| **entity_agent** | "Module master of Entity Extraction" | JSON `{entities: [...]}` | Direct extraction, no visible reasoning |
| **relationship_agent** | "Expert in identifying relationships" | JSON `{relationships: [...]}` | Direct extraction, no visible reasoning |
| **notes** | "Watson" (Sherlock's assistant) | JSON `{additions, removals, summary}` | Implicit note-taking logic |

### Current Prompt Patterns

1. **Role Definition**: All agents have personas in system prompts
2. **JSON Output**: Specialized agents mandate structured JSON responses
3. **Two-Layer Architecture**: System prompt (persona) + User prompt (task details)
4. **FILE_CONTENT Handling**: All agents treat file contents as primary sources
5. **No Explicit Reasoning Format**: Reasoning is implicit or prose-based

---

## Proposed Thinking Format

### Notation System

```
fact 1 > conclusion 1
fact 2, fact 3 > conclusion 2
conclusion 1, conclusion 2 > ... > conclusion 3
```

| Symbol | Meaning | Example |
|--------|---------|---------|
| `,` | AND conjunction | `fact 1, fact 2` = both facts together |
| `>` | Direct inference | `A > B` = A leads to B |
| `...` | Thought leap / intuition | `A > ... > B` = A leads to B through implicit steps |
| `;` | Chain separator | End of one inference chain |

### Format Structure

```
## Thinking

### Facts
- F1: [observed fact]
- F2: [observed fact]
- F3: [observed fact]

### Reasoning
F1 > C1;
F2, F3 > C2;
C1, C2 > ... > C3

### Conclusion
[Final answer based on C3]
```

---

## Implementation Plan

### Phase 1: Default Agent (Primary User-Facing)

**File**: `src/qq/agents/default/default.system.md`

**Changes**:
1. Add "Thinking Format" section after response guidelines
2. Define the notation system
3. Provide examples of when to use structured thinking
4. Make it optional for simple queries, required for complex reasoning

**New Section**:
```markdown
## Thinking Format

For complex questions, structure your reasoning using this compact notation:

**Facts**: Label observations (F1, F2, ...)
**Inference**: Use `>` to show direct conclusions
**Thought Leaps**: Use `...` when intuition bridges gaps
**Chains**: Separate inference chains with `;`

Example:
```
### Facts
- F1: User has MongoDB running on port 27017
- F2: Connection timeout errors in logs
- F3: MongoDB logs show no connection attempts

### Reasoning
F1, F2 > C1: Service is up but not receiving connections;
F3 > C2: Requests aren't reaching MongoDB;
C1, C2 > ... > C3: Likely a firewall or binding issue

### Answer
Check if MongoDB is bound to localhost only (`bindIp` setting).
```

Use this format when:
- Debugging complex issues
- Answering multi-step questions
- Making recommendations with tradeoffs
- Explaining architectural decisions
```

### Phase 2: Notes Agent (Watson Persona)

**Files**:
- `src/qq/agents/notes/notes.system.md`
- `src/qq/agents/notes/notes.user.md`

**Changes**:
1. Enhance Watson persona to include deductive reasoning notation
2. Add thinking field to JSON output (optional)
3. Use format to justify importance classifications

**System Prompt Update**:
```markdown
You are Watson. Sherlock Holmes' best friend and assistant.
You are meticulous and intelligent. You reason through observations methodically:

F1, F2 > conclusion; conclusion, F3 > ... > insight

This notation captures your deductive process:
- `,` joins facts
- `>` shows inference
- `...` marks intuitive leaps
- `;` ends a chain

You will be given a conversation and fulfill the request with the best notes.
Start your response with {
```

**JSON Output Extension**:
```json
{
  "thinking": "F1: user mentioned name 'Alex'; F2: multiple references > C1: core identity fact",
  "additions": [...],
  "removals": [...],
  "summary": "..."
}
```

### Phase 3: Entity Agent

**Files**:
- `src/qq/agents/entity_agent/entity_agent.system.md`
- `src/qq/agents/entity_agent/entity_agent.user.md`

**Changes**:
1. Add reasoning field to justify entity type selection
2. Use format for ambiguous entity resolution

**JSON Output Extension**:
```json
{
  "entities": [
    {
      "name": "MongoNotesStore",
      "type": "Class",
      "description": "MongoDB-backed notes storage",
      "reasoning": "F1: class keyword, F2: inherits BaseStore > Class type"
    }
  ]
}
```

### Phase 4: Relationship Agent

**Files**:
- `src/qq/agents/relationship_agent/relationship_agent.system.md`
- `src/qq/agents/relationship_agent/relationship_agent.user.md`

**Changes**:
1. Add reasoning field for relationship type selection
2. Especially useful for distinguishing similar types (USES vs DEPENDS_ON)

**JSON Output Extension**:
```json
{
  "relationships": [
    {
      "source": "App",
      "target": "MongoNotesStore",
      "type": "USES",
      "description": "App uses MongoNotesStore for persistence",
      "reasoning": "F1: import statement, F2: method calls > USES not DEPENDS_ON (runtime use)"
    }
  ]
}
```

---

## Detailed File Changes

### 1. default.system.md

**Location**: `src/qq/agents/default/default.system.md`

**Add after "## How to respond" section**:

```markdown
## Structured Thinking

For complex reasoning, use compact inference notation:

**Notation**:
- Facts: `F1:`, `F2:` ... labeled observations
- Inference: `>` direct conclusion
- Thought leap: `...` intuitive bridge
- Chain end: `;`

**Format**:
```
### Observations
- F1: [fact]
- F2: [fact]

### Reasoning
F1, F2 > C1: [conclusion];
C1, F3 > ... > C2: [insight]

### Answer
[Response based on reasoning]
```

**When to use**:
- Multi-step debugging
- Architectural decisions
- Tradeoff analysis
- Complex explanations

**When NOT to use**:
- Simple factual answers
- Code generation
- Direct commands
```

### 2. notes.system.md

**Location**: `src/qq/agents/notes/notes.system.md`

**Replace with**:

```markdown
You are Watson. Sherlock Holmes' best friend and assistant.
You are meticulous and intelligent, reasoning through observations methodically.

Your deductive notation:
- `F1, F2 > conclusion` — facts lead to conclusion
- `> ... >` — intuitive leap
- `;` — end of chain

Example: `F1: user said "I'm Alex", F2: repeated 3 times > core identity fact`

You will be given a conversation and a request. Fulfill it with the best notes.
Start your response with {
```

### 3. notes.user.md

**Location**: `src/qq/agents/notes/notes.user.md`

**Add to output format section**:

```markdown
Your output MUST be valid JSON:
{
  "thinking": "F1: ...; F2: ... > C1; ...",  // Optional: your reasoning chain
  "additions": [...],
  "removals": [...],
  "summary": "..."
}
```

### 4. entity_agent.system.md

**Location**: `src/qq/agents/entity_agent/entity_agent.system.md`

**Replace with**:

```markdown
You are a master of Entity Extraction.
You assess important entities and bind multi-word names: John Doe -> "John Doe"

For ambiguous cases, note your reasoning:
`F1: class keyword, F2: has methods > Class type`

Respond in JSON starting with {
```

### 5. relationship_agent.system.md

**Location**: `src/qq/agents/relationship_agent/relationship_agent.system.md`

**Replace with**:

```markdown
You are an expert in identifying relationships between entities.
You analyze conversations and entity lists to determine connections.

For ambiguous relationship types, note your reasoning:
`F1: import present, F2: called in method > USES (not DEPENDS_ON)`

Respond in JSON starting with {
```

---

## Testing Strategy

### Test Cases for Default Agent

1. **Simple query** (should NOT use format):
   - Input: "What time is it?"
   - Expected: Direct answer, no thinking block

2. **Debug query** (should use format):
   - Input: "Why is my MongoDB connection failing?"
   - Expected: Facts listed, reasoning chain, actionable answer

3. **Architecture question** (should use format):
   - Input: "Should I use Redis or MongoDB for caching?"
   - Expected: Facts about requirements, tradeoff reasoning, recommendation

### Test Cases for Notes Agent

1. **Verify JSON still valid** with optional thinking field
2. **Verify importance classification** has reasoning traces
3. **Verify deduplication decisions** are explained

### Test Cases for Entity/Relationship Agents

1. **Ambiguous entity type**: Verify reasoning field explains choice
2. **Similar relationship types**: Verify USES vs DEPENDS_ON distinction explained

---

## Rollout Plan

| Phase | Scope | Risk | Validation |
|-------|-------|------|------------|
| 1 | Default agent only | Low | Manual testing |
| 2 | Notes agent | Medium | JSON schema validation |
| 3 | Entity agent | Low | Output format tests |
| 4 | Relationship agent | Low | Output format tests |

### Phase 1 Rollout (Default Agent)

1. Update `default.system.md`
2. Test with 10 varied prompts
3. Verify simple queries don't over-use format
4. Verify complex queries show clear reasoning

### Phase 2-4 Rollout (Specialized Agents)

1. Add optional `thinking`/`reasoning` fields to output schemas
2. Update system and user prompts
3. Verify JSON parsing still works (backward compatible)
4. Run through extraction test suite

---

## Success Metrics

1. **Traceability**: Can trace how agent reached conclusion
2. **Debuggability**: Easier to spot reasoning errors
3. **Consistency**: Similar inputs produce similar reasoning patterns
4. **Backward Compatibility**: Existing JSON consumers unaffected

---

## Open Questions

1. **Verbosity control**: Should there be a flag to enable/disable thinking output?
2. **Storage**: Should thinking chains be persisted for debugging?
3. **Token cost**: Does structured thinking significantly increase token usage?
4. **User preference**: Some users may prefer prose reasoning over notation

---

## Appendix: Full Notation Reference

```
NOTATION QUICK REFERENCE

Facts:
  F1: [observation]        Named fact
  F2: [observation]        Another fact

Operators:
  ,                        AND (combine facts)
  >                        Infer (direct conclusion)
  ...                      Leap (intuitive jump)
  ;                        End chain

Patterns:
  F1 > C1                  Single fact inference
  F1, F2 > C1              Multiple facts inference
  F1 > ... > C1            Fact to conclusion via leap
  C1, C2 > C3              Conclusions combine
  C1, F3 > ... > C2        Mixed with leap

Full Example:
  F1: Server returns 500
  F2: Logs show DB timeout
  F3: DB CPU at 100%

  F1, F2 > C1: DB issue causing failures;
  F3 > C2: DB overloaded;
  C1, C2 > ... > C3: Need to scale or optimize DB
```
