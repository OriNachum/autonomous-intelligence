# Investigation: File Content Not Saved to Memory System

**Date:** 2026-02-03
**Status:** Root Cause Identified
**Issue:** When the agent reads files via `read_file` tool, the content is not persisted to the memory layers (Notes/MongoDB, Knowledge Graph/Neo4j)

## Summary

Tool outputs (including file content from `read_file`) are not captured in the conversation history. Since the memory agents (NotesAgent, KnowledgeGraphAgent) rely on conversation history to extract knowledge, file content never reaches the memory system.

## Root Cause

The conversation history only records:
1. User messages
2. Final assistant responses

It does **not** record:
- Tool calls
- Tool results (including file content)

### Evidence in Code

**app.py (lines 160-172, 230-242):**
```python
# Strands Agent execution
response = agent(formatted_message)

# Only user message and final response are saved
history.add("user", message)
history.add("assistant", str(response))

# Memory agents process this limited history
messages = history.get_messages()
if notes_agent:
    notes_agent.process_messages(messages)
```

**history.py (lines 60-69):**
```python
def add(self, role: str, content: str) -> None:
    """Add a message to history and save."""
    self._messages.append({
        "role": role,
        "content": content,
        "timestamp": datetime.now().isoformat(),
    })
```

No mechanism exists to capture "tool" or "tool_result" roles.

## Data Flow Analysis

### Current Flow (Broken)

```
User: "Read README.md and summarize it"
    │
    ▼
Agent calls read_file("README.md")
    │
    ▼
FileManager returns file content (1000 lines)
    │
    ▼
LLM processes content, generates summary
    │
    ▼
History saves:
  - user: "Read README.md and summarize it"
  - assistant: "Here's the summary: [condensed]"
    │
    ▼
NotesAgent.process_messages() receives:
  - USER: Read README.md and summarize it
  - ASSISTANT: Here's the summary: [condensed]
    │
    ▼
Result: Only the summary is available for extraction
        Original file content is LOST
```

### Expected Flow (Not Implemented)

```
History should save:
  - user: "Read README.md and summarize it"
  - tool_call: read_file("README.md")
  - tool_result: [full file content]
  - assistant: "Here's the summary: [condensed]"
    │
    ▼
NotesAgent would receive full file content
    │
    ▼
Result: Entities, facts, and relationships from file
        content would be extracted and persisted
```

## Affected Components

| Component | File | Issue |
|-----------|------|-------|
| App orchestration | `src/qq/app.py` | Only saves user/assistant messages |
| History class | `src/qq/history.py` | No support for tool roles |
| Agent execution | `src/qq/agents/__init__.py` | Tool results not exposed |
| NotesAgent | `src/qq/agents/notes/notes.py` | Processes limited history |
| KnowledgeGraphAgent | `src/qq/services/graph.py` | Same limitation |
| EntityAgent | `src/qq/agents/entity_agent/` | Same limitation |
| RelationshipAgent | `src/qq/agents/relationship_agent/` | Same limitation |

## Strands Agent Framework Limitation

The Strands Agent framework handles tool execution internally. The `agent(message)` call returns only the final text response. There's no built-in way to:
1. Intercept tool calls before execution
2. Access tool results after execution
3. Get a structured response with tool call history

## Recommended Fixes

### Option 1: Capture Tool Execution from Strands Agent

Investigate if Strands Agent provides:
- A callback/hook mechanism for tool execution
- Access to the full message history including tool calls
- A way to retrieve tool execution logs

### Option 2: Wrap Tool Functions to Log Results

```python
def create_logged_tool(tool_func, history):
    @tool
    def logged_tool(*args, **kwargs):
        result = tool_func(*args, **kwargs)
        history.add("tool_result", f"{tool_func.__name__}: {result[:5000]}")
        return result
    return logged_tool
```

### Option 3: Post-Process Agent Response

If Strands Agent stores tool execution in its internal state, extract and save it after `agent(message)` returns.

### Option 4: Explicit Memory Save for File Reads

Add a dedicated code path that saves file content directly to memory when `read_file` is called:

```python
@tool
def read_file(path: str) -> str:
    content = file_manager.read_file(path)
    # Directly save to notes/knowledge graph
    memory_service.save_file_content(path, content)
    return content
```

## Additional Considerations

1. **Chunking**: Large files may need to be chunked before sending to memory agents
2. **Deduplication**: Avoid saving the same file content multiple times
3. **Relevance filtering**: Not all file content may be worth persisting
4. **Token limits**: Memory agent prompts have token limits; tool outputs can be large

## Conclusion

The memory system architecture assumes all relevant information flows through conversation history. However, tool outputs bypass history entirely, creating a gap where file content (and other tool results) are never persisted to long-term memory.

This is a fundamental architectural issue that requires extending the history capture mechanism to include tool execution data.

---

## Implemented Solution (2026-02-03)

### Automatic File Content Capture to History

File reads are now automatically added to conversation history, allowing the memory agents (NotesAgent, KnowledgeGraphAgent) to process file content alongside regular conversation.

**Implementation:**

1. **`src/qq/services/file_manager.py`**:
   - Module-level registry `_pending_file_reads` stores file read metadata
   - `read_file()` appends each read to the registry
   - `get_pending_file_reads()` and `clear_pending_file_reads()` expose the registry

2. **`src/qq/app.py`**:
   - `_format_file_quote()` formats file content as a quoted history entry
   - `_capture_file_reads_to_history()` adds pending reads to history after agent execution
   - Called in both `run_cli_mode()` and `run_console_mode()` before memory agents run

**History format:**
```
[Quote from file: config.yaml (lines 1-50 of 120)]
---
<file content here>
---
[End of quote from config.yaml]
```

**Data flow (fixed):**
```
User: "Read config.yaml and summarize"
    │
    ▼
Agent calls read_file("config.yaml")
    │
    ▼
FileManager returns content + registers in _pending_file_reads
    │
    ▼
LLM generates response
    │
    ▼
app.py captures file reads to history:
  - user: "Read config.yaml and summarize"
  - file_content: "[Quote from file: config.yaml...]"
  - assistant: "Here's the summary..."
    │
    ▼
NotesAgent + KnowledgeGraphAgent process full history
    │
    ▼
Result: File content is now available for memory extraction
```

**Benefits:**
- Automatic - no agent action required
- Memory agents see actual file content, not just summaries
- Each file chunk is clearly labeled with filename and line range
- Works for partial file reads (sliding window)

---

## Additional Fix: Prompt Updates (2026-02-03)

### Issue
File content was captured to history but memory agents weren't extracting information from it because prompts didn't explicitly mention `FILE_CONTENT` messages.

### Changes

**1. Updated prompts to explicitly handle FILE_CONTENT:**

- `notes.user.md`: Added instruction to extract from FILE_CONTENT messages, added "File Knowledge" section
- `entity_agent.user.md`: Added instruction to extract entities from files (classes, functions, configs), added new entity types (File, Function, Class, Configuration)
- `relationship_agent.user.md`: Added instruction to extract code relationships, added new relationship types (IMPORTS, EXTENDS, IMPLEMENTS, CALLS, DEPENDS_ON, CONFIGURES, CONTAINS)

**2. Updated NotesManager:**

- `notes.py`: Added "File Knowledge" section to template and `apply_diff()` section list

**Prompt excerpt (notes.user.md):**
```
**IMPORTANT:** Messages with role FILE_CONTENT contain actual file contents
that were read. These are a PRIMARY source of information - extract facts,
entities, configuration details, code patterns, and any other useful knowledge
from file content.
```
