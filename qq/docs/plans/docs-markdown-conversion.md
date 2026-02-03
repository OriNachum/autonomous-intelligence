# Plan: Document Conversion Support (DOCX/PDF/XLSX)

## Goal
Enable `qq` agents to transparently read, search, and process rich document formats (`.pdf`, `.docx`, `.xlsx`, `.pptx`) by converting them to Markdown on the fly. This will allow the existing `read_file` capability to serve rich content to the `NotesAgent`, `KnowledgeGraphAgent`, and the main user-facing agent.

## Strategy
We will integrate the `MarkItDown` library into the `FileManager` service. This "smart" integration means `read_file` will automatically detect supported binary formats and convert them to Markdown, allowing all agents to "see" the content of these files without requiring special handling for each format.

## Implementation Details

### 1. Dependencies
Add `markitdown` to `pyproject.toml`.
Note: `markitdown` handles format parsing locally. For advanced features (OCR in PDFs), additional system dependencies like `tesseract` would be needed, but we will focus on text extraction first.

### 2. Service Layer: `FileManager` Update
Modify `src/qq/services/file_manager.py` to include a `DocumentReader` class (or helper) and update existing methods.

#### New Helper: `DocumentReader`
Encapsulate `MarkItDown` logic to handle lazy loading and error management.
```python
class DocumentReader:
    def __init__(self):
        self._md = None

    @property
    def md(self):
        if self._md is None:
            # Lazy import to avoid startup overhead if not used
            from markitdown import MarkItDown
            self._md = MarkItDown()
        return self._md

    def convert(self, path: Path) -> str:
        try:
            result = self.md.convert(str(path))
            return result.text_content
        except Exception as e:
            return f"Error converting detected binary file '{path.name}': {e}"
```

#### Update: `FileManager.read_file`
Update `read_file` to inspect the file extension or MIME type.
*   If text-based (py, md, txt, json): Read as text (existing behavior).
*   If document-based (pdf, docx, xlsx, pptx): Delegate to `DocumentReader`.

```python
    def read_file(self, path: str) -> str:
        target_path = self._resolve_path(path)
        if not target_path.exists():
            return "Error..."
            
        # Extension check
        suffix = target_path.suffix.lower()
        if suffix in ['.pdf', '.docx', '.xlsx', '.pptx']:
             return self.document_reader.convert(target_path)
             
        # Fallback to text
        return target_path.read_text()
```

### 3. Agent Integration
Because we are modifying the service layer (`FileManager`), **no changes are needed in the agents themselves**.
*   **Main Agent**: When user asks "read report.docx", `read_file` tool returns Markdown.
*   **Notes/Graph Agents**: If they scan directory and read files, they will receive clean Markdown text to process.

### 4. Alternative: "Converter Agent"
The user asked to "add an agent". While a dedicated `ConverterAgent` could be created (e.g., to batch convert files in the background), the direct integration into `FileManager` is more powerful for the current Architecture:
*   **Pros of integration**: Immediate use by all agents.
*   **Pros of separate Agent**: Asynchronous processing, observing a "drop folder".

**Decision**: We will proceed with the **Integration approach** (Smart `read_file`) as it fulfills the user's core need ("convert them to markdown") most efficiently. If asynchronous batch processing is required later, a `DocumentIngestionAgent` can be built on top of this updated `FileManager`.

## Execution Steps
1.  Update `pyproject.toml` with `markitdown`.
2.  Update `src/qq/services/file_manager.py` to implement `DocumentReader` and modify `read_file`.
3.  Verify by reading a sample `.docx` or `.pdf` using `qq read_file`.
