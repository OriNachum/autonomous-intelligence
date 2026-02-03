# Plan: Sliding Window for `read_file`

## Goal
Enable `qq` to read large files by implementing a "sliding window" mechanism in the `read_file` tool.
This ensures the agent can read files of any size without exceeding context window limits, by processing them in line-based chunks.

## Core Mechanisms
1.  **Line-Based Window**: The tool operates strictly on line numbers (`start_line`, `num_lines`). No artificial "pages".
2.  **Binary Conversion**: For binary files (PDF, DOCX), the file is **first converted to Markdown text**, and then the line extraction is applied to the converted text.
3.  **Hard Limit**: The tool will return a maximum of **200 lines** per call to manage context usage.
4.  **Agent-Driven Loop**: The tool provides content and metadata (total lines); the **Agent** is responsible for deciding whether to request the next chunk.

## Proposed Changes

### 1. `src/qq/services/file_manager.py`

#### Constants
*   `MAX_LINES_PER_READ = 200`

#### Update `FileManager.read_file`

**Signature**:
```python
def read_file(self, path: str, start_line: int = 1, num_lines: int = MAX_LINES_PER_READ) -> str:
```

**Parameters**:
*   `path`: File path.
*   `start_line`: The starting line number (1-indexed). Default `1`.
*   `num_lines`: The number of lines to read. Default `200`. **Capped at 200**.

**Logic**:
1.  **Resolve Path**: (Existing logic).
2.  **Get Content**:
    *   **Binary (PDF, etc.)**: Convert to Markdown string using `self.document_reader`. This happens *prior* to line slicing.
    *   **Text**: Read string directly.
3.  **Process Content**:
    *   `all_lines = content.splitlines()`
    *   `total_lines = len(all_lines)`
    *   **Enforce Limit**:
        *   `effective_num_lines = min(num_lines, MAX_LINES_PER_READ)`
    *   **Calculate Line Range**:
        *   `start_index = start_line - 1`
        *   `end_index = start_index + effective_num_lines`
        *   `end_index = min(end_index, total_lines)`
    *   **Validation**:
        *   If `start_index >= total_lines`: Return message "Start line {start_line} is out of bounds. Total lines: {total_lines}."
    *   **Extract Lines**:
        *   `selected_lines = all_lines[start_index:end_index]`
        *   `output_text = "\n".join(selected_lines)`
    *   **Format Output with Metadata**:
        *   Prepend a header meant for the agent:
            ```
            [File: {filename} | Lines {start_line}-{end_index} of {total_lines}]
            [Note: Output limited to {MAX_LINES_PER_READ} lines max per request.]
            ----------------------------------------
            {output_text}
            ```

### 2. Usage Pattern (Agent Loop)
The Agent interacts with the file in a loop:

1.  **Call 1**: `read_file("doc.pdf", start_line=1, num_lines=200)`
    *   (System converts PDF -> MD, then extracts lines 1-200)
    *   **Output**: `[Lines 1-200 of 450...] ...content...`
    *   **Agent Decision**: "I have 450 lines. I need to read the rest."
2.  **Call 2**: `read_file("doc.pdf", start_line=201, num_lines=200)`
    *   **Output**: `[Lines 201-400 of 450...] ...content...`
    *   **Agent Decision**: "Still more."
3.  **Call 3**: `read_file("doc.pdf", start_line=401, num_lines=200)`
    *   **Output**: `[Lines 401-450 of 450...] ...content...`
    *   **Agent Decision**: "Done."

## Verification Plan

### Manual Verification
1.  **Setup**: Create `test_large.txt` with 300 lines.
2.  **Test Limit enforcement**:
    *   Call `read_file("test_large.txt", start_line=1, num_lines=500)`
    *   **Verify**: Returns only 200 lines (1-200).
    *   **Verify**: Header says "Lines 1-200 of 300".
3.  **Test Sliding**:
    *   Call `read_file("test_large.txt", start_line=201, num_lines=200)`
    *   **Verify**: Returns lines 201-300.
    *   **Verify**: Header says "Lines 201-300 of 300".
4.  **Test PDF**:
    *   (Optional, if PDF test file available) Call `read_file("test.pdf", start_line=1)`
    *   Verify it returns Markdown text with line limits applied.
