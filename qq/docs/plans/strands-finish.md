# Strands Agents Migration Plan

## Goal
Replace all instances of direct `openai` or custom `VLLMClient` usage with `strands-agents` library components (`Agent`, `OpenAIModel`), ensuring consistent agent interaction patterns across the entire application.

## User Review Required
> [!IMPORTANT]
> This migration modifies how `NotesAgent` and `KnowledgeGraphAgent` intersect with the LLM backend. The custom `VLLMClient` at `src/qq/client.py` will be removed.

## Proposed Changes

### 1. Infrastructure (`src/qq/agents/`)
#### [MODIFY] [__init__.py](file:///home/spark/git/autonomous-intelligence/qq/src/qq/agents/__init__.py)
- Extract `OpenAIModel` configuration logic from `load_agent` into a reusable `get_model()` function.
- Ensure `get_model()` handles environment variables (`VLLM_URL`, `OPENAI_API_KEY`, etc.) consistently.

### 2. Memory Agents Migration
Each agent class currently accepting `llm_client` will be updated to accept a `strands.models.Model` instance (or use `get_model` internally if appropriate, but dependency injection is better).

#### [MODIFY] [notes.py](file:///home/spark/git/autonomous-intelligence/qq/src/qq/agents/notes/notes.py)
- Update `NotesAgent.__init__` to accept `model: Any` instead of `llm_client`.
- In `process_messages`:
    - Instantiate a temporary `strands.Agent` with the shared `model` and the dynamically loaded system prompt.
    - Call the agent with the user prompt: `response = agent(prompt)`.
    - Continue to use existing `parse_json_response` to handle valid/invalid JSON and `<think>` tags.

#### [MODIFY] [graph.py](file:///home/spark/git/autonomous-intelligence/qq/src/qq/services/graph.py)
- Update `KnowledgeGraphAgent.__init__` to accept `model`.
- Pass `model` to `EntityAgent` and `RelationshipAgent` constructors.

#### [MODIFY] [entity_agent.py](file:///home/spark/git/autonomous-intelligence/qq/src/qq/agents/entity_agent/entity_agent.py)
- Update `EntityAgent.__init__` to accept `model`.
- In `extract`:
    - Instantiate `strands.Agent` with `model` and the system prompt.
    - Call agent to get response.

#### [MODIFY] [relationship_agent.py](file:///home/spark/git/autonomous-intelligence/qq/src/qq/agents/relationship_agent/relationship_agent.py)
- Update `RelationshipAgent.__init__` to accept `model`.
- In `extract`:
    - Instantiate `strands.Agent` with `model` and the system prompt.
    - Call agent to get response.

### 3. Cleanup
#### [DELETE] [client.py](file:///home/spark/git/autonomous-intelligence/qq/src/qq/client.py)
- Remove the stale `VLLMClient` implementation.

### 4. Application Entry Point
#### [MODIFY] [app.py](file:///home/spark/git/autonomous-intelligence/qq/src/qq/app.py)
- Update commented-out memory agent initialization code to reflect the new API (passing `model` from `load_agent` or `get_model()` instead of `client`).
- Remove `create_client` import and usage.

## Verification Plan

### Automated Tests
- Run `qq --help` to ensure no import errors.
- Run `pytest src/qq/test_systems.py` (if applicable, or create a new verification script).

### Manual Verification
- Since memory agents are currently disabled in `app.py`, verification primarily involves ensuring the code is valid and imports are correct.
- If possible, temporarily enable memory agents in `app.py` and run a simple CLI query to verify they don't crash and attempt to call the model (logs will show "Sending HTTP Request").
