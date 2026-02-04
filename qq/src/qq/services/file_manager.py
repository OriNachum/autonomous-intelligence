"""File management with session-isolated state.

The FileManager now stores all state (pending file reads, working directory)
at the instance level to support parallel QQ execution without race conditions.
"""

import os
import json
import re
from pathlib import Path
from fnmatch import fnmatch
from typing import List, Optional, Dict

MAX_LINES_PER_READ = 100


class DocumentReader:
    """Lazy-loading document converter for binary formats (PDF, DOCX, etc.)."""

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


class FileManager:
    """File operations manager with session-isolated state.

    All mutable state (pending file reads, working directory) is stored
    at the instance level, not as module globals. This enables parallel
    QQ execution without race conditions.

    State is persisted to:
      <state_dir>/files_state.json
    """

    def __init__(self, state_dir: Path):
        """Initialize FileManager with a state directory.

        Args:
            state_dir: Directory to store state file (typically session dir)
        """
        self.state_dir = state_dir
        self.state_file = self.state_dir / "files_state.json"

        # Instance-level state (no more module globals!)
        self.pending_file_reads: List[Dict[str, str]] = []

        # Ensure state directory exists
        self.state_dir.mkdir(parents=True, exist_ok=True)

        self._cwd = os.getcwd()
        self._load_state()
        self.document_reader = DocumentReader()

    def get_pending_file_reads(self) -> List[Dict[str, str]]:
        """Get list of files read since last clear.

        Each item has 'path', 'name', 'content', 'start_line', 'end_line', 'total_lines'.
        """
        return list(self.pending_file_reads)

    def clear_pending_file_reads(self) -> None:
        """Clear the pending file reads registry."""
        self.pending_file_reads.clear()

    def _load_state(self):
        """Load state from file."""
        if self.state_file.exists():
            try:
                data = json.loads(self.state_file.read_text())
                saved_cwd = data.get("cwd")
                if saved_cwd and os.path.exists(saved_cwd) and os.path.isdir(saved_cwd):
                    self._cwd = saved_cwd
            except json.JSONDecodeError:
                pass  # Ignore corrupt state file

    def _save_state(self):
        """Save state to file."""
        data = {"cwd": self._cwd}
        self.state_file.write_text(json.dumps(data))

    @property
    def cwd(self) -> str:
        return self._cwd

    @cwd.setter
    def cwd(self, path: str):
        self._cwd = path
        self._save_state()

    def _resolve_path(self, path: str) -> Path:
        """Resolve path relative to cwd if it's not absolute."""
        p = Path(path)
        if not p.is_absolute():
            p = Path(self.cwd) / p
        return p.resolve()

    def set_directory(self, path: str) -> str:
        """
        Sets the current working directory for file operations.

        Args:
            path: Absolute or relative path to the directory.

        Returns:
            Success message or error description.
        """
        try:
            target_path = self._resolve_path(path)

            if not target_path.exists():
                return f"Error: Directory '{target_path}' does not exist."

            if not target_path.is_dir():
                return f"Error: '{target_path}' is not a directory."

            self.cwd = str(target_path)
            return f"Current directory set to: {self.cwd}"
        except Exception as e:
            return f"Error setting directory: {e}"

    def list_files(self, pattern: str = "*", recursive: bool = False, use_regex: bool = False) -> str:
        """
        Lists files in the current working directory.

        Args:
            pattern: Glob pattern or Regex pattern to filter files. Defaults to "*".
            recursive: If True, lists files recursively.
            use_regex: If True, treats 'pattern' as a regex.

        Returns:
            List of files matched.
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
                        # Should not happen if p is from iterdir/rglob of cwd_path,
                        # but good for safety if we change iterator logic
                        continue

            if not files:
                return "No files found matching the criteria."

            return "\\n".join(sorted(files))
        except Exception as e:
            return f"Error listing files: {e}"

    def read_file(self, path: str, start_line: int = 1, num_lines: int = MAX_LINES_PER_READ) -> str:
        """
        Reads the content of a file with a sliding window mechanism.

        Args:
            path: Absolute or relative path to the file.
            start_line: The starting line number (1-indexed). Default 1.
            num_lines: The number of lines to read. Default 100. Capped at 100.

        Returns:
            File content chunk with metadata or error message.
        """
        try:
            target_path = self._resolve_path(path)

            if not target_path.exists():
                return f"Error: File '{target_path}' does not exist."

            if not target_path.is_file():
                return f"Error: '{target_path}' is not a file."

            # 1. Get Content
            # Extension check for binary files
            suffix = target_path.suffix.lower()
            if suffix in ['.pdf', '.docx', '.xlsx', '.pptx']:
                content = self.document_reader.convert(target_path)
            else:
                content = target_path.read_text()

            # 2. Process Content
            all_lines = content.splitlines()
            total_lines = len(all_lines)

            # Enforce Limit
            effective_num_lines = min(num_lines, MAX_LINES_PER_READ)

            # Calculate Line Range
            # start_line is 1-indexed, so convert to 0-indexed
            start_index = start_line - 1
            if start_index < 0:
                start_index = 0

            end_index = start_index + effective_num_lines
            effective_end_index = min(end_index, total_lines)

            # Validation
            if start_index >= total_lines and total_lines > 0:
                return f"Start line {start_line} is out of bounds. Total lines: {total_lines}."

            if total_lines == 0:
                return f"[File: {target_path.name} is empty]"

            extracted_lines = all_lines[start_index:effective_end_index]
            output_text = "\n".join(extracted_lines)

            # 3. Format Output with Metadata
            display_end_line = start_index + len(extracted_lines)

            header = (
                f"[File: {target_path.name} | Lines {start_line}-{display_end_line} of {total_lines}]\n"
                f"[Note: Output limited to {MAX_LINES_PER_READ} lines max per request.]\n"
                "----------------------------------------"
            )

            # 4. Add Footer Guidance
            if display_end_line < total_lines:
                next_start = display_end_line + 1
                footer = (
                    f"\n----------------------------------------\n"
                    f"[Note: to read more of the file, request this again with start-line {next_start}; total lines: {total_lines}]"
                )
            else:
                footer = (
                    f"\n----------------------------------------\n"
                    f"[File read completed. Total lines: {total_lines}]"
                )

            # 5. Register this file read for history capture (instance-level, not global)
            self.pending_file_reads.append({
                "path": str(target_path),
                "name": target_path.name,
                "content": output_text,
                "start_line": start_line,
                "end_line": display_end_line,
                "total_lines": total_lines,
            })

            return f"{header}\n{output_text}{footer}"

        except Exception as e:
            return f"Error reading file '{path}': {e}"
