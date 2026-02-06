# Token Overflow Management Plan

**Status:** IMPLEMENTED
**Priority:** High
**Related:** `docs/investigations/overwhelming-context-on-listing-files.md`

## Problem Summary

Tool outputs (especially `list_files`) can exceed the model's context window, causing unrecoverable session state. The existing token recovery mechanism only reduces conversation history, which cannot help when a single tool output is 30x larger than the context limit.

---

## Implementation Phases

### Phase 1: Pre-flight Count Check (P0)

**Goal:** Prevent `list_files` from returning overwhelming output by checking count first.

**Threshold:** Warn if >20 files match (per user specification).

**File:** `src/qq/services/file_manager.py`

**Changes to `list_files` method (lines 136-179):**

```python
MAX_FILES_WARNING_THRESHOLD = 20

def list_files(self, pattern: str = "*", recursive: bool = False, use_regex: bool = False) -> str:
    """
    Lists files in the current working directory.

    Args:
        pattern: Glob pattern or Regex pattern to filter files. Defaults to "*".
        recursive: If True, lists files recursively.
        use_regex: If True, treats 'pattern' as a regex.

    Returns:
        List of files matched, or warning if too many files.
    """
    try:
        cwd_path = Path(self.cwd)
        files = []

        if recursive:
            iterator = cwd_path.rglob("*")
        else:
            iterator = cwd_path.iterdir()

        for p in iterator:
            if p.is_file():
                try:
                    rel_path = p.relative_to(cwd_path)
                    rel_path_str = str(rel_path)

                    if use_regex:
                        if re.search(pattern, rel_path_str):
                            files.append(rel_path_str)
                    else:
                        if fnmatch(rel_path_str, pattern):
                            files.append(rel_path_str)
                except ValueError:
                    continue

        if not files:
            return "No files found matching the criteria."

        # Pre-flight count check: warn if exceeds threshold
        if len(files) > MAX_FILES_WARNING_THRESHOLD:
            mode = "recursively" if recursive else "in current directory"
            return (
                f"Warning: {len(files)} files match pattern '{pattern}' {mode}.\n"
                f"Listing all would overwhelm the context window.\n\n"
                f"Options:\n"
                f"1. Use count_files() to see breakdown by extension\n"
                f"2. Use a more specific pattern (e.g., '*.py' instead of '*')\n"
                f"3. Use list_files with offset/limit: list_files(pattern, offset=0, limit=20)\n\n"
                f"To proceed anyway, use: list_files(pattern, offset=0, limit={len(files)})"
            )

        return "\n".join(sorted(files))
    except Exception as e:
        return f"Error listing files: {e}"
```

**Constant location:** Add at module level (after `MAX_LINES_PER_READ = 100`):

```python
MAX_FILES_WARNING_THRESHOLD = 20
```

---

### Phase 2: Pagination for list_files (P0)

**Goal:** Add offset/limit parameters to `list_files` like `read_file` has.

**File:** `src/qq/services/file_manager.py`

**New signature:**

```python
MAX_FILES_PER_LIST = 100

def list_files(
    self,
    pattern: str = "*",
    recursive: bool = False,
    use_regex: bool = False,
    offset: int = 0,
    limit: int = 0,  # 0 means use warning check, >0 bypasses check
) -> str:
```

**Full implementation:**

```python
MAX_FILES_PER_LIST = 100
MAX_FILES_WARNING_THRESHOLD = 20

def list_files(
    self,
    pattern: str = "*",
    recursive: bool = False,
    use_regex: bool = False,
    offset: int = 0,
    limit: int = 0,
) -> str:
    """
    Lists files in the current working directory with optional pagination.

    Args:
        pattern: Glob pattern or Regex pattern to filter files. Defaults to "*".
        recursive: If True, lists files recursively.
        use_regex: If True, treats 'pattern' as a regex.
        offset: Skip first N files (for pagination). Default 0.
        limit: Max files to return. 0 = use warning threshold, then suggest pagination.

    Returns:
        List of files matched with metadata, or warning if too many files.
    """
    try:
        cwd_path = Path(self.cwd)
        files = []

        if recursive:
            iterator = cwd_path.rglob("*")
        else:
            iterator = cwd_path.iterdir()

        for p in iterator:
            if p.is_file():
                try:
                    rel_path = p.relative_to(cwd_path)
                    rel_path_str = str(rel_path)

                    if use_regex:
                        if re.search(pattern, rel_path_str):
                            files.append(rel_path_str)
                    else:
                        if fnmatch(rel_path_str, pattern):
                            files.append(rel_path_str)
                except ValueError:
                    continue

        if not files:
            return "No files found matching the criteria."

        total_count = len(files)
        files = sorted(files)

        # If no explicit limit, apply warning threshold check
        if limit == 0:
            if total_count > MAX_FILES_WARNING_THRESHOLD:
                mode = "recursively" if recursive else "in current directory"
                return (
                    f"Warning: {total_count} files match pattern '{pattern}' {mode}.\n"
                    f"Listing all would overwhelm the context window.\n\n"
                    f"Options:\n"
                    f"1. Use count_files() to see breakdown by extension\n"
                    f"2. Use a more specific pattern (e.g., '*.py' instead of '*')\n"
                    f"3. Use list_files with pagination: list_files('{pattern}', offset=0, limit=20)\n"
                )
            # Under threshold, return all
            return "\n".join(files)

        # Explicit limit provided - apply pagination
        effective_limit = min(limit, MAX_FILES_PER_LIST)
        paginated = files[offset:offset + effective_limit]

        if not paginated:
            return f"No files in range. Total: {total_count}, offset: {offset}"

        # Build output with metadata
        start_idx = offset + 1
        end_idx = offset + len(paginated)

        header = f"[Files {start_idx}-{end_idx} of {total_count}]"

        if end_idx < total_count:
            next_offset = offset + effective_limit
            footer = f"\n[More files available. Use offset={next_offset} to continue.]"
        else:
            footer = f"\n[Listing complete. Total: {total_count} files]"

        return f"{header}\n" + "\n".join(paginated) + footer

    except Exception as e:
        return f"Error listing files: {e}"
```

**Update tool wrapper in `src/qq/agents/__init__.py` (lines 161-171):**

```python
@tool
def list_files(
    pattern: str = "*",
    recursive: bool = False,
    use_regex: bool = False,
    offset: int = 0,
    limit: int = 0,
) -> str:
    """
    List files in the current session directory with pagination.

    Args:
        pattern: Filter files by glob pattern (default "*") or regex.
        recursive: Whether to search recursively.
        use_regex: If True, pattern is treated as regex.
        offset: Skip first N files (for pagination). Default 0.
        limit: Max files to return. 0 = auto (warns if >20, suggests pagination).

    Returns:
        File listing with metadata, or warning with options if too many files.
    """
    return file_manager.list_files(pattern, recursive, use_regex, offset, limit)
```

---

### Phase 3: Tool Output Size Guard (P1)

**Goal:** Add a safety wrapper that truncates any tool output exceeding a safe threshold.

**File:** `src/qq/services/output_guard.py` (NEW)

```python
"""Tool output size guard to prevent context overflow."""

import os
from typing import Callable, Any

# Configuration
MAX_TOOL_OUTPUT_CHARS = int(os.getenv("QQ_MAX_TOOL_OUTPUT", "28000"))  # ~8K tokens
CHARS_PER_TOKEN = float(os.getenv("QQ_CHARS_PER_TOKEN", "3.5"))


def guard_output(output: str, tool_name: str = "tool") -> str:
    """
    Truncate tool output if it would overwhelm context.

    Args:
        output: The raw tool output string.
        tool_name: Name of the tool (for error message).

    Returns:
        Original output if under limit, truncated with warning otherwise.
    """
    if len(output) <= MAX_TOOL_OUTPUT_CHARS:
        return output

    # Truncate at line boundary
    truncated = output[:MAX_TOOL_OUTPUT_CHARS]
    last_newline = truncated.rfind('\n')
    if last_newline > MAX_TOOL_OUTPUT_CHARS * 0.8:
        truncated = truncated[:last_newline]

    est_tokens = int(len(output) / CHARS_PER_TOKEN)
    shown_tokens = int(len(truncated) / CHARS_PER_TOKEN)

    return (
        f"{truncated}\n\n"
        f"[OUTPUT TRUNCATED]\n"
        f"Tool '{tool_name}' returned ~{est_tokens} tokens, showing first ~{shown_tokens}.\n"
        f"Use more specific parameters or pagination to get remaining data."
    )


def wrap_tool(tool_fn: Callable[..., str], tool_name: str = None) -> Callable[..., str]:
    """
    Wrap a tool function to guard its output.

    Args:
        tool_fn: The tool function to wrap.
        tool_name: Optional name override (defaults to function name).

    Returns:
        Wrapped function with output guarding.
    """
    name = tool_name or getattr(tool_fn, '__name__', 'tool')

    def wrapped(*args, **kwargs) -> str:
        result = tool_fn(*args, **kwargs)
        if isinstance(result, str):
            return guard_output(result, name)
        return result

    # Preserve function metadata
    wrapped.__name__ = tool_fn.__name__
    wrapped.__doc__ = tool_fn.__doc__
    return wrapped
```

**Integration in `src/qq/agents/__init__.py`:**

Add import and wrap high-risk tools:

```python
from qq.services.output_guard import guard_output

# In _create_common_tools, modify list_files:
@tool
def list_files(...) -> str:
    """..."""
    result = file_manager.list_files(pattern, recursive, use_regex, offset, limit)
    return guard_output(result, "list_files")
```

---

### Phase 4: Recovery Enhancement (P1)

**Goal:** Detect tool output overflow and provide clearer recovery path.

**File:** `src/qq/errors.py`

**Add overflow severity detection:**

```python
def classify_overflow(info: TokenLimitInfo) -> str:
    """
    Classify the severity of token overflow.

    Returns:
        'minor': <1000 tokens over, history reduction may help
        'major': 1000-50000 tokens over, aggressive reduction needed
        'catastrophic': >50000 tokens over, likely tool output problem
    """
    if info is None:
        return 'unknown'

    if info.overflow < 1000:
        return 'minor'
    elif info.overflow < 50000:
        return 'major'
    else:
        return 'catastrophic'
```

**File:** `src/qq/recovery.py`

**Add overflow classification to RecoveryResult:**

```python
from qq.errors import parse_token_error, classify_overflow

@dataclass
class RecoveryResult:
    """Result of agent execution with recovery."""
    success: bool
    response: Optional[Any] = None
    attempts: int = 0
    strategy: str = "normal"
    tokens_reduced: int = 0
    error: Optional[Exception] = None
    warnings: List[str] = field(default_factory=list)
    overflow_severity: str = "none"  # NEW: none, minor, major, catastrophic
```

**Update execute method to set overflow_severity:**

```python
def execute(self, ...):
    # ... existing logic ...

    except Exception as e:
        is_token, info = parse_token_error(e)

        if not is_token:
            return RecoveryResult(success=False, error=e, ...)

        severity = classify_overflow(info) if info else 'unknown'

        # For catastrophic overflow, don't bother retrying with history reduction
        if severity == 'catastrophic':
            return RecoveryResult(
                success=False,
                error=e,
                attempts=attempt + 1,
                strategy="tool_output_overflow",
                overflow_severity=severity,
                warnings=[
                    "A tool returned too much data for the context window.",
                    "Use more specific parameters or pagination.",
                ],
            )

        # Continue with normal retry logic for minor/major...
```

**File:** `src/qq/app.py`

**Update console mode to handle catastrophic overflow:**

```python
if not result.success:
    if result.overflow_severity == 'catastrophic':
        console.print_error(
            "[Tool output too large]\n"
            "A tool returned more data than the model can process.\n"
            "Session context cleared. Try a more specific query.\n"
            "Tip: Use count_files() before list_files() on large directories."
        )
        history.clear()
        file_manager.clear_pending_file_reads()
        continue  # Skip to next input prompt

    elif is_token_error(result.error):
        # Normal history clear for non-catastrophic overflow
        console.print_warning("[Clearing history for fresh start]")
        history.clear()
        # ... existing retry logic ...
```

---

## File Changes Summary

| File | Action | Description |
|------|--------|-------------|
| `src/qq/services/file_manager.py` | MODIFY | Add pagination (offset/limit), pre-flight count check (>20 warning) |
| `src/qq/agents/__init__.py` | MODIFY | Update list_files tool signature, add output guard |
| `src/qq/services/output_guard.py` | CREATE | Tool output size guard utility |
| `src/qq/errors.py` | MODIFY | Add `classify_overflow()` function |
| `src/qq/recovery.py` | MODIFY | Add `overflow_severity` to RecoveryResult, handle catastrophic |
| `src/qq/app.py` | MODIFY | Handle catastrophic overflow with clear messaging |

---

## Constants Reference

| Constant | Value | Location | Description |
|----------|-------|----------|-------------|
| `MAX_FILES_WARNING_THRESHOLD` | 20 | file_manager.py | Warn if more files match |
| `MAX_FILES_PER_LIST` | 100 | file_manager.py | Max files per paginated request |
| `MAX_TOOL_OUTPUT_CHARS` | 28000 | output_guard.py | ~8K tokens, truncation threshold |
| `QQ_MAX_TOOL_OUTPUT` | env var | output_guard.py | Override for MAX_TOOL_OUTPUT_CHARS |
| `QQ_CHARS_PER_TOKEN` | 3.5 | output_guard.py | Token estimation ratio |

---

## Testing Plan

### Unit Tests

1. **list_files warning threshold:**
   - Create temp dir with 25 files, verify warning returned
   - Create temp dir with 15 files, verify listing returned

2. **list_files pagination:**
   - Create 50 files, request offset=0, limit=20, verify 20 returned with metadata
   - Request offset=40, limit=20, verify 10 returned with "complete" message
   - Verify header shows correct "Files X-Y of Z"

3. **Output guard:**
   - Test output under threshold passes through
   - Test output over threshold is truncated at line boundary
   - Verify truncation message includes token estimates

4. **Overflow classification:**
   - Test minor (<1000 tokens over)
   - Test major (1000-50000)
   - Test catastrophic (>50000)

### Integration Tests

1. **End-to-end pagination:**
   - Agent lists large directory, gets warning
   - Agent uses pagination, gets paginated results
   - Agent continues with offset, completes listing

2. **Recovery path:**
   - Simulate large tool output
   - Verify catastrophic overflow detected
   - Verify session resets cleanly
   - Verify user can continue

### Manual Tests

1. Navigate to large codebase (e.g., linux kernel)
2. Run `list_files("*", recursive=True)`
3. Verify warning appears with count
4. Use pagination to browse safely
5. Verify no session crash

---

## Implementation Order

1. **Phase 1:** Pre-flight count check in `file_manager.py` (quick win, prevents most issues)
2. **Phase 2:** Pagination in `file_manager.py` + tool wrapper update
3. **Phase 3:** Output guard (defense in depth)
4. **Phase 4:** Recovery enhancement (better UX when overflow happens)

---

## Success Criteria

1. `list_files` with >20 matches returns warning instead of file list
2. `list_files` with explicit limit returns paginated results with metadata
3. Tool outputs exceeding 28K chars are truncated with helpful message
4. Catastrophic overflow (>50K tokens) triggers immediate session reset with clear guidance
5. No more "996201 input tokens" errors causing unrecoverable state
