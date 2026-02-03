import os
import json
import re
from pathlib import Path
from fnmatch import fnmatch
from typing import List, Optional

class FileManager:
    def __init__(self, state_dir: Path):
        self.state_dir = state_dir
        self.state_file = self.state_dir / "files_state.json"
        
        # Ensure state directory exists
        self.state_dir.mkdir(parents=True, exist_ok=True)
        
        self._cwd = os.getcwd()
        self._load_state()

    def _load_state(self):
        """Load state from file."""
        if self.state_file.exists():
            try:
                data = json.loads(self.state_file.read_text())
                saved_cwd = data.get("cwd")
                if saved_cwd and os.path.exists(saved_cwd) and os.path.isdir(saved_cwd):
                    self._cwd = saved_cwd
            except json.JSONDecodeError:
                pass # Ignore corrupt state file

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

    def read_file(self, path: str) -> str:
        """
        Reads the content of a file.
        
        Args:
            path: Absolute or relative path to the file.
        
        Returns:
            File content or error message.
        """
        try:
            target_path = self._resolve_path(path)
            
            if not target_path.exists():
                return f"Error: File '{target_path}' does not exist."
                
            if not target_path.is_file():
                 return f"Error: '{target_path}' is not a file."
            
            return target_path.read_text()
        except Exception as e:
             return f"Error reading file '{path}': {e}"
