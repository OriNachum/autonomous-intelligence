# Plan: Turn QQ into a Strands Agent (OpenAI Model / vLLM)

This document outlines the plan to refactor `qq` to utilize the `strands-agent` library using its `OpenAIModel` interface, pointing to our existing `vllm` backend.

## 1. Objectives

- **Refactor `qq`**: Convert the core `qq` logic to use `strands-agent` SDK.
- **Model Provider**: Configure `strands.OpenAIModel` to point to the local `vllm` instance.
  - **Backend**: `vllm` (serving OpenAI-compatible API).
  - **Interface**: `OpenAIModel` from `strands-agents`.
- **Architecture**: Adopt the patterns found in `strands-agent` documentation (Agent-as-a-Tool, Orchestrator).

## 2. Prerequisites

- **Library Installation**: Install the Python Strands Agents SDK.
  ```bash
  pip install strands-agents
  ```
- **Environment Variables**:
  - `OPENAI_API_BASE`: Set to the vLLM endpoint (e.g., `http://localhost:8000/v1`).
  - `OPENAI_API_KEY`: Set to a dummy value (e.g., `EMPTY`) or real key if vLLM requires it.
  - `MODEL_NAME`: The name of the model served by vLLM.

## 3. Architecture Transition

### Current Architecture
- **Client**: `qq/client.py` uses direct `openai` or `vllm` client calls.
- **Agents**: Simple dataclasses/directories in `src/qq/agents/` containing prompts.
- **Execution**: `app.py` manages the loop, history, and injects context into the system prompt.
- **Tools**: Handled via custom `skills` and `mcp_tools`.

### New Architecture (Strands Native)
- **Agent**: The main `qq` instance will be a `strands.Agent`.
- **Model**: `strands.models.OpenAIModel` configured with `base_url` pointing to vLLM.
- **Orchestrator Pattern**: The main agent acts as an Orchestrator. It can route tasks to specialized sub-agents or tools.
- **Tools**:
  - Existing `skills` (and MCP tools) should be wrapped as Strands `@tool` functions.
  - **Memory Agents** (`notes`, `graph`) can be exposed as tools or kept as background hooks.

## 4. Implementation Plan

### Phase 1: Core Integration
1.  **Refactor `load_agent` (`src/qq/agents/__init__.py`)**:
    - Modify to instantiate and return a `strands.Agent`.
    - Configure the `Agent` to use `OpenAIModel` pointing to vLLM.
    ```python
    from strands import Agent
    from strands.models import OpenAIModel
    
    # Configure Model to use vLLM
    model = OpenAIModel(
        model=os.getenv("MODEL_NAME", "model-name"),
        base_url=os.getenv("OPENAI_API_BASE", "http://localhost:8000/v1"),
        api_key=os.getenv("OPENAI_API_KEY", "EMPTY")
    )
    
    # Example instantiation
    agent = Agent(
        name=name,
        system_prompt=loaded_system_prompt,
        model=model,
        tools=[...] 
    )
    ```

2.  **Update `app.py` Loop**:
    - Replace `client.chat(...)` with `agent(user_input)` or `agent.invoke(user_input)`.
    - Ensure streaming is handled correctly with `strands` callbacks if needed.

### Phase 2: Tool Migration
1.  **Wrap Skills**:
    - Create a utility to convert `qq`'s existing dynamic skills into Strands `@tool` definitions.
    - Pass these tools to the `Agent` constructor in `load_agent`.

2.  **Wrap MCP Tools**:
    - Adapt `mcp_loader` to convert MCP tools into Strands compatible tools.

### Phase 3: Multi-Agent / Memory Integration
1.  **Memory as Tools**:
    - **Context Retrieval**: Verify optimal insertion point (system prompt vs memory module).
    - **Graph/Notes**: Wrap as Tools (`@tool`) to allow the agent to actively "Save Note" or "Query Graph", or maintain as background hooks if preferred for latency.

### Phase 4: Verification
- Verify `qq` connects to vLLM via `OpenAIModel`.
- Verify `qq` still remembers user (Memory persistence).
- Verify `qq` can still use skills.

## 5. Definition of Done
- `docs/strands-agent-openai-model.md` exists (This file).
- `qq` architecture plan is clear and updated for vLLM usage.
