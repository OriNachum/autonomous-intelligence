# Investigation: Overwhelming Context on File Listing

**Date:** 2026-02-06
**Status:** Investigation Complete, Solutions Proposed
**Severity:** High - Causes unrecoverable session state

## Problem Statement

When `list_files` is called with a broad pattern (e.g., `*` with `recursive=True`), the tool can return an enormous number of file paths that overwhelms the model's context window. This causes:

1. Token limit exceeded (996,201 input tokens vs 32,768 limit)
2. Recovery mechanism fails (all retry strategies exhausted)
3. History cleared as last resort
4. User work and conversation context lost

**Error observed:**
```
[Token limit: retrying with window_10]
[Token limit: retrying with window_5]
[Token limit: retrying with window_2]
[Token limit: retrying with window_0]
[Token limit: retrying with minimal]
[Clearing history for fresh start]
Error: Unrecoverable: Error code: 400 - {'error': {'message': "This model's maximum context length is 32768 tokens. However, your request has 996201 input tokens..."}}
```

---

## Root Cause Analysis

### 1. list_files Has No Output Limits

**Current implementation (`file_manager.py:136-179`):**

```python
def list_files(self, pattern: str = "*", recursive: bool = False, use_regex: bool = False) -> str:
    # ... matching logic ...
    return "\\n".join(sorted(files))  # ALL matching files returned
```

Unlike `read_file` which enforces `MAX_LINES_PER_READ = 100`, `list_files` has no limits on:
- Number of files returned
- Total output size
- Token count estimation

### 2. Recovery Mechanism Targets Wrong Problem

**Current recovery strategy (`recovery.py:29`):**

```python
WINDOW_SIZES = [20, 10, 5, 2, 0]  # Reduces HISTORY window
```

The recovery mechanism progressively reduces conversation **history**, but the problem is in the **current tool output**. When a single tool response exceeds the context limit, history reduction cannot help.

**The math:**
- Model context: ~32,768 tokens
- Single tool output: ~996,201 tokens (30x the limit)
- History window reduction: Irrelevant - even with 0 history, the tool output alone is 30x too large

### 3. No Pre-flight Size Check

The tool executes fully before any size validation. By the time the agent receives the response, it's already too late - the oversized content is in the message buffer.

---

## Comparison with read_file

| Aspect | read_file | list_files |
|--------|-----------|------------|
| Output limit | 100 lines max | None |
| Pagination | Yes (start_line, num_lines) | No |
| Size estimate | Header shows total lines | No indication |
| User guidance | "request again with start-line N" | None |

`read_file` is well-designed for large content:
```
[File: config.yaml | Lines 1-100 of 5000]
[Note: Output limited to 100 lines max per request.]
...
[Note: to read more, request with start-line 101; total lines: 5000]
```

`list_files` provides no such safety:
```
file1.py
file2.py
... (potentially 100,000+ lines)
```

---

## Data Flow Analysis

### Failure Scenario

```
User: "List all files in this directory"
    │
    ▼
Agent calls list_files("*", recursive=True)
    │
    ▼
FileManager.list_files() returns 50,000 file paths (~1M tokens)
    │
    ▼
Agent receives tool result, context now ~1M tokens
    │
    ▼
API call with 996,201 tokens → 400 Error (exceeds 32,768 limit)
    │
    ▼
TokenRecovery reduces history window: 20 → 10 → 5 → 2 → 0
    │
    ▼
Still fails: tool output alone is 996,201 tokens
    │
    ▼
history.clear() called as last resort
    │
    ▼
Still fails: current message still contains the huge tool output
    │
    ▼
Unrecoverable state - entire session must be restarted
```

### Why History Clear Doesn't Help

The `execute_with_recovery` function clears history but the oversized content is in the **current turn's message array**, not in history:

```python
# In app.py line 340-341
history.clear()
response = agent(user_input)  # user_input doesn't include the tool result
```

However, the agent framework's internal state still holds the tool result from the previous invocation. The framework doesn't expose a way to selectively remove tool results from the current turn.

---

## Existing Safeguards (Insufficient)

### 1. count_files Tool Exists

`file_manager.py:181-255` provides a `count_files` function that returns safe summaries:

```
Directory: /home/user/project
Pattern: *
Total files recursively: 12,847

By extension:
  .py: 3,421
  .md: 892
  .json: 456
```

But this requires the agent (or model) to know to call it first.

### 2. Child Process Output Limit

`QQ_MAX_OUTPUT=50000` chars limits output from child processes, but `list_files` is a direct tool call, not a child process.

---

## Proposed Solutions

### Solution 1: Add Pagination to list_files (Recommended)

Add limits and pagination like `read_file`:

```python
MAX_FILES_PER_LIST = 100

def list_files(
    self,
    pattern: str = "*",
    recursive: bool = False,
    use_regex: bool = False,
    offset: int = 0,          # NEW: Skip first N files
    limit: int = MAX_FILES_PER_LIST,  # NEW: Max files to return
) -> str:
    # ... existing matching logic ...

    # Apply pagination
    total_count = len(files)
    files = sorted(files)[offset:offset + limit]

    # Add metadata header
    header = f"[Files {offset + 1}-{offset + len(files)} of {total_count}]"

    if offset + len(files) < total_count:
        footer = f"\n[More files available. Use offset={offset + limit} to continue.]"
    else:
        footer = f"\n[Listing complete. Total: {total_count} files]"

    return f"{header}\n" + "\n".join(files) + footer
```

### Solution 2: Pre-flight Count Check

Check file count before listing, warn if large:

```python
def list_files(self, pattern: str = "*", recursive: bool = False, ...) -> str:
    # Pre-flight count
    cwd_path = Path(self.cwd)
    iterator = cwd_path.rglob("*") if recursive else cwd_path.iterdir()

    count = sum(1 for p in iterator if p.is_file() and self._matches(p, pattern, use_regex))

    if count > 500:
        return (
            f"Warning: {count} files match this pattern.\n"
            f"This would overwhelm the context. Consider:\n"
            f"1. Use count_files() first to see breakdown by extension\n"
            f"2. Use a more specific pattern (e.g., '*.py' instead of '*')\n"
            f"3. Use list_files with limit parameter: list_files(pattern, limit=100)\n"
        )

    # Proceed with normal listing...
```

### Solution 3: Tool Output Size Guard

Add a middleware/wrapper that truncates any tool output exceeding a threshold:

```python
MAX_TOOL_OUTPUT_TOKENS = 8000  # Leave room for system prompt and response
CHARS_PER_TOKEN = 3.5

def guard_tool_output(output: str, tool_name: str) -> str:
    """Truncate tool output if it would overwhelm context."""
    max_chars = int(MAX_TOOL_OUTPUT_TOKENS * CHARS_PER_TOKEN)

    if len(output) <= max_chars:
        return output

    truncated = output[:max_chars]
    lines = truncated.rsplit('\n', 1)[0]  # Don't cut mid-line

    return (
        f"{lines}\n\n"
        f"[OUTPUT TRUNCATED: {tool_name} returned ~{len(output)} chars "
        f"(~{int(len(output)/CHARS_PER_TOKEN)} tokens), showing first "
        f"~{max_chars} chars. Use more specific parameters to get remaining data.]"
    )
```

### Solution 4: Recovery Enhancement for Tool Output Overflow

Add a new recovery strategy that handles tool output overflow specifically:

```python
class RecoveryResult:
    # ... existing fields ...
    tool_output_overflow: bool = False  # NEW

def execute_with_recovery(...):
    # ... existing logic ...

    except Exception as e:
        is_token, info = parse_token_error(e)

        if is_token and info and info.overflow > 100000:
            # Massive overflow - likely tool output problem, not history
            return RecoveryResult(
                success=False,
                error=e,
                strategy="tool_output_overflow",
                tool_output_overflow=True,
                warnings=[
                    "A tool returned too much data for the context window.",
                    "The session will restart. Use more specific tool parameters.",
                ],
            )
```

### Solution 5: Agent System Prompt Guidance

Add to agent system prompts:

```markdown
## File Listing Best Practices

Before listing files:
1. Use `count_files` to check how many files match your pattern
2. If count > 100, use a more specific pattern (e.g., `*.py` not `*`)
3. Always prefer specific patterns over wildcards
4. For large directories, list subdirectories first, then drill down
```

---

## Implementation Priority

| Solution | Impact | Effort | Priority |
|----------|--------|--------|----------|
| 1. Pagination in list_files | High | Medium | P0 |
| 2. Pre-flight count check | High | Low | P0 |
| 3. Tool output size guard | Medium | Medium | P1 |
| 4. Recovery enhancement | Medium | Low | P1 |
| 5. System prompt guidance | Low | Low | P2 |

---

## Recovery Reset Mechanism

After an overwhelming tool output, the current session state is corrupted. We need a mechanism to reset more aggressively than just clearing history:

### Proposed: Hard Reset

```python
def hard_reset(agent, history, console):
    """Complete reset after unrecoverable tool output overflow."""

    # 1. Clear conversation history
    history.clear()

    # 2. Notify user
    console.print_warning(
        "[A tool returned too much data. Session reset required.]\n"
        "[Your previous work is preserved in memory, but conversation context is cleared.]\n"
        "[Tip: Use count_files() before list_files() on large directories.]"
    )

    # 3. Reset file manager state
    file_manager.clear_pending_file_reads()

    # 4. Log for debugging
    logger.error("Hard reset triggered due to tool output overflow")
```

### Integration Point

In `app.py`, after the final recovery failure:

```python
if not result.success:
    if is_token_error(result.error):
        overflow = getattr(result, 'tokens_overflow', 0)

        if overflow > 100000:
            # Catastrophic tool output - hard reset
            hard_reset(agent, history, console)
            console.print_info("Session reset. Please try a more specific query.")
            continue  # Skip to next input
        else:
            # Normal history clear should help
            console.print_warning("[Clearing history for fresh start]")
            history.clear()
```

---

## Testing Recommendations

1. **Unit test**: Pagination in list_files with various offsets/limits
2. **Unit test**: Pre-flight count check threshold behavior
3. **Integration test**: Simulate large directory listing, verify truncation
4. **Integration test**: Verify recovery from tool output overflow
5. **Manual test**: Confirm user can continue after hard reset

---

## Related Issues

- `docs/plans/max-tokens-limit-recovery.md` - General token recovery (implemented)
- `docs/investigations/agentic-memory-read-files.md` - File content capture (implemented)
- Token estimation utilities in `src/qq/tokens.py` (pending implementation)

---

## Conclusion

The `list_files` tool lacks the protective limits that exist in `read_file`. When called on large directories, it can produce output 30x larger than the model's context window. The current recovery mechanism cannot handle this because it targets conversation history rather than the current tool output.

**Immediate fixes needed:**
1. Add pagination to `list_files` (like `read_file`)
2. Add pre-flight count check with warning threshold
3. Add hard reset mechanism for catastrophic overflow

These changes would prevent the unrecoverable state while maintaining full functionality through pagination.
