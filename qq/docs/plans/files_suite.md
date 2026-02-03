# Files Suite Implementation Plan

This plan outlines the addition of a native file tool suite to the `qq` agent, enabling file system interaction with persistent working directory state.

## Goal
Add `read_file`, `list_files`, and `set_directory` tools to `qq` that:
1.  Allow setting and persisting a "current working directory" for the session.
2.  List files with wildcard/regex filtering, supporting relative paths.
3.  Read files using absolute or relative paths.

## Proposed Changes

### 1. New Service: `FileManager`
Create `src/qq/services/file_manager.py` to handle file operations and state.

#### Class `FileManager`
*   **State Management**:
    *   `__init__(self, state_dir: Path)`: Initializes with a directory to store state.
    *   `state_file`: Points to `state_dir / "files_state.json"`.
    *   `cwd`: Property that reads/writes the current path to `state_file`. Defaults to process CWD if no state exists.
*   **Methods**:
    *   `set_directory(path: str) -> str`:
        *   Resolves path (handling relative paths against current `cwd`).
        *   Verifies path exists and is a directory.
        *   Updates `cwd` state and saves to disk.
        *   Returns success message.
    *   `list_files(pattern: str = "*", recursive: bool = False, use_regex: bool = False) -> str`:
        *   Lists files in `cwd`.
        *   Applies glob `pattern` or regex based on `use_regex`.
        *   Returns list of files (names/paths).
    *   `read_file(path: str) -> str`:
        *   Resolves `path` against `cwd`.
        *   Reads content.
        *   Returns content or error message.

### 2. Integration: `src/qq/agents/__init__.py`
Modify `load_agent` to inject these tools.

*   Import `FileManager` from `qq.services.file_manager`.
*   Determine storage path using logic similar to `History` implementation (using `~/.qq/<agent_name>`).
*   Instantiate `FileManager`.
*   Wrap `FileManager` methods using `strands.tool`.
*   Append these tools to the `agent_tools` list before creating the `Agent`.

## Verification Plan

### Manual Verification
1.  Run `qq -m "set_directory to /tmp"`
    *   Verify response confirms change.
    *   Verify `~/.qq/<agent>/files_state.json` is created/updated.
2.  Run `qq -m "list_files"`
    *   Verify it lists `/tmp` content.
3.  Run `qq -m "list_files pattern='*.txt'"` (or similar).
    *   Verify filtering.
4.  Run `qq -m "read_file 'somefile.txt'"`
    *   Verify content reading.
5.  Restart `qq` (new CLI command) and verify `list_files` still uses `/tmp`.
