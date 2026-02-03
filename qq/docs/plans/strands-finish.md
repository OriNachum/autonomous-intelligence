# Plan: Finish Migration to Strands Agents

This plan outlines the final steps to fully migrate the `qq` application to use the `strands` library for all LLM interactions, replacing the direct `vllm` / `openai` client usage in the memory and graph agents.

## Goal
Remove all legacy `create_client()` calls and direct `OpenAI` client usage. Ensure `NotesAgent`, `EntityAgent`, and `RelationshipAgent` utilize the `strands` library (specifically `strands.Agent` and `strands.models.OpenAIModel`) for their operations.

## User Review Required
> [!IMPORTANT]
> This refactor changes how the memory and graph agents interact with the LLM. We are replacing the `llm_client.chat` method calls with `strands.Agent` execution or direct model usage via `strands`.
> The `app.py` file will also be modified to uncomment and re-enable the memory agents.

## Proposed Changes

### Refactor Memory Agents
The following agents currently depend on a raw `llm_client` (OpenAI compatible client). They will be updated to accept a `strands.models.OpenAIModel` (or `strands.models.Model`) and use `strands.Agent` internally.

#### [MODIFY] [notes.py](file:///home/spark/git/autonomous-intelligence/qq/src/qq/agents/notes/notes.py)
- Change `__init__` to accept `model` instead of `llm_client`.
- In `process_messages`:
  - Construct a `strands.Agent` using the dynamically loaded system prompt and the provided `model`.
  - Use `agent(user_prompt)` to get the response.
  - Parse the response (the existing JSON parsing logic can remain or be simplified if `strands` handles cleanup, though `strands` output is raw text).

#### [MODIFY] [entity_agent.py](file:///home/spark/git/autonomous-intelligence/qq/src/qq/agents/entity_agent/entity_agent.py)
- Change `__init__` to accept `model` instead of `llm_client`.
- In `extract`:
  - Create a temporary `strands.Agent` with the entity extraction system prompt.
  - Call the agent with the formatted user prompt.

#### [MODIFY] [relationship_agent.py](file:///home/spark/git/autonomous-intelligence/qq/src/qq/agents/relationship_agent/relationship_agent.py)
- Change `__init__` to accept `model` instead of `llm_client`.
- In `extract`:
  - Create a temporary `strands.Agent` with the relationship extraction system prompt.
  - Call the agent with the formatted user prompt.

#### [MODIFY] [graph.py](file:///home/spark/git/autonomous-intelligence/qq/src/qq/services/graph.py)
- Update `KnowledgeGraphAgent` to accept `model` instead of `llm_client`.
- Pass this `model` to the `EntityAgent` and `RelationshipAgent` instances.

### Update Application Entry Point

#### [MODIFY] [app.py](file:///home/spark/git/autonomous-intelligence/qq/src/qq/app.py)
- Remove `create_client` import and usage.
- Retrieve the `model` from the loaded main agent (e.g., `agent.model`).
- **Uncomment** the initialization of `NotesAgent`, `KnowledgeGraphAgent`, and `ContextRetrievalAgent`.
- Pass `model=agent.model` to `NotesAgent` and `KnowledgeGraphAgent`.

## Verification Plan

### Automated Tests
- Run `qq` in console mode.
- Verify that `qq` starts without errors.

### Manual Verification
- Send a message in `qq` console that contains factual information (e.g., "My name is saved in notes").
- Check `logs/notes_agent.log` to see if the Notes Agent effectively called the LLM and extracted the note.
- Check `logs/graph_agent.log` to see if entities were extracted.
