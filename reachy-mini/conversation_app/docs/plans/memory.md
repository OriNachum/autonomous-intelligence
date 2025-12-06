# Memory Implementation Plan

## Goal Description
Introduce a persistent memory system to `conversation_app`. This involves saving context in a loadable "memento" file, loading it on startup, and updating it after conversations by extracting important details using an agent. This is a preparation step for a future RAG system with a vector database.

## User Review Required
> [!IMPORTANT]
> The "memento" file will be stored as a JSON file in `conversation_app/data/memento.json`.
> The extraction process will trigger in background thread or process an additional LLM call after each response (or periodically), which might increase latency or cost if using a paid API (though currently using local vLLM).

## Proposed Changes

### conversation_app

#### [NEW] [memory_manager.py](file:///home/thor/git/autonomous-intelligence/reachy-mini/conversation_app/memory_manager.py)
- Create `MemoryManager` class.
- **Methods**:
    - `__init__(self, file_path, model_name, api_url)`: Initialize with file path and LLM config.
    - `load_memory(self)`: Load memory from JSON file. Returns a formatted string for context.
    - `save_memory(self, memory_data)`: Save memory to JSON file.
    - `update_memory(self, last_user_message, last_assistant_response, current_memory)`:
        - Construct a prompt for the "Memory Agent".
        - The prompt will include the current memory, the new interaction, and instructions to extract facts, remove conflicts, and update the structure.
        - Call the LLM (vLLM) to get the updated memory JSON.
        - Save the new memory.
        - Returns the updated memory string.

#### [MODIFY] [app.py](file:///home/thor/git/autonomous-intelligence/reachy-mini/conversation_app/app.py)
- Import `MemoryManager`.
- In `__init__`:
    - Initialize `MemoryManager`.
- In `initialize`:
    - Call `self.memory_manager.load_memory()`.
    - Update `self.system_prompt` or insert a new system message with the loaded memory.
- In `process_message`:
    - After generating the response, trigger `self.memory_manager.update_memory` (potentially in the background to avoid blocking, but `process_message` is async so we can await it or spawn a task).
    - Update the active context with the new memory for the *next* turn.

#### [NEW] [agents/memory/memory_update.system.md](file:///home/thor/git/autonomous-intelligence/reachy-mini/conversation_app/agents/memory/memory_update.system.md)
- System prompt for the Memory Agent.
- Instructions:
    - You are a Memory Manager.
    - Input: Current Memory (JSON), New Interaction (User/Assistant).
    - Output: Updated Memory (JSON).
    - Rules: Extract key details, update existing facts, resolve conflicts (prefer newer info), remove outdated info.

## Verification Plan

### Automated Tests
- Create `tests/test_memory_manager.py`:
    - Test `load_memory` with missing file (should return empty/default).
    - Test `save_memory`.
    - Test `update_memory` (mocking the LLM call).

### Manual Verification
1.  **Startup**: Run `python conversation_app.py`. Check logs to see if memory is loaded.
2.  **Interaction**: Speak to Reachy (e.g., "My name is Thor").
3.  **Update**: Check logs/file to see if `memento.json` is updated with "User's name is Thor".
4.  **Persistence**: Restart the app. Ask "What is my name?". Verify Reachy remembers.
