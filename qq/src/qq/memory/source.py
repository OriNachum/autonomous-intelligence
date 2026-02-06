"""Source metadata collection for provenance tracking.

Collects file checksums, git metadata, and conversation context
to attach to every piece of stored knowledge (notes, entities, relationships).
"""

import hashlib
import logging
import os
import subprocess
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from functools import lru_cache
from pathlib import Path
from typing import Optional, Dict, Any, List

logger = logging.getLogger("qq.source")

# Cache git repo metadata to avoid repeated subprocess calls
_git_repo_cache: Dict[str, Dict[str, str]] = {}


@dataclass
class SourceRecord:
    """Provenance metadata for a piece of stored knowledge."""

    # Origin type: "file", "conversation", "user_input", "derived"
    source_type: str

    # File source (when source_type == "file")
    file_path: Optional[str] = None
    file_name: Optional[str] = None
    line_start: Optional[int] = None
    line_end: Optional[int] = None
    checksum: Optional[str] = None

    # Git source (populated if file is in a git repo)
    git_repo: Optional[str] = None
    git_branch: Optional[str] = None
    git_commit: Optional[str] = None
    git_author: Optional[str] = None

    # Conversation source
    session_id: Optional[str] = None
    agent_id: Optional[str] = None
    timestamp: Optional[str] = None

    # Quality signals
    confidence: Optional[float] = None
    extraction_model: Optional[str] = None

    def __post_init__(self):
        if self.timestamp is None:
            self.timestamp = datetime.now(timezone.utc).isoformat()

    @property
    def source_id(self) -> str:
        """Unique ID for this source. Shared between MongoDB and Neo4j."""
        if self.source_type == "file" and self.checksum:
            return self.checksum
        if self.session_id:
            return f"session:{self.session_id}"
        return f"unknown:{self.timestamp}"

    def to_dict(self) -> Dict[str, Any]:
        """Serialize to dict for storage."""
        d = asdict(self)
        d["source_id"] = self.source_id
        return {k: v for k, v in d.items() if v is not None}

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "SourceRecord":
        """Deserialize from dict."""
        # Remove source_id (computed property) before constructing
        data = {k: v for k, v in data.items() if k != "source_id"}
        # Only pass known fields
        known = {f.name for f in cls.__dataclass_fields__.values()}
        filtered = {k: v for k, v in data.items() if k in known}
        return cls(**filtered)

    def to_neo4j_properties(self) -> Dict[str, Any]:
        """Flatten to Neo4j-compatible flat properties with source_ prefix."""
        d = self.to_dict()
        result = {}
        for k, v in d.items():
            if isinstance(v, (str, int, float, bool)):
                result[f"source_{k}"] = v
        return result


def compute_file_checksum(file_path: str) -> Optional[str]:
    """Compute SHA-256 checksum of a file's content."""
    try:
        h = hashlib.sha256()
        with open(file_path, "rb") as f:
            for chunk in iter(lambda: f.read(8192), b""):
                h.update(chunk)
        return f"sha256:{h.hexdigest()}"
    except (OSError, IOError) as e:
        logger.debug(f"Could not compute checksum for {file_path}: {e}")
        return None


def _run_git(args: List[str], cwd: str) -> Optional[str]:
    """Run a git command and return stdout, or None on failure."""
    try:
        result = subprocess.run(
            ["git"] + args,
            cwd=cwd,
            capture_output=True,
            text=True,
            timeout=5,
        )
        if result.returncode == 0:
            return result.stdout.strip()
    except (subprocess.TimeoutExpired, FileNotFoundError):
        pass
    return None


def collect_git_metadata(file_path: str) -> Dict[str, str]:
    """Collect git metadata for a file.

    Returns dict with git_repo, git_branch, git_commit, git_author.
    Returns empty dict if file is not in a git repo.
    Results are cached per repo root.
    """
    file_dir = str(Path(file_path).parent)

    # Find repo root
    repo_root = _run_git(["rev-parse", "--show-toplevel"], cwd=file_dir)
    if not repo_root:
        return {}

    # Check cache for repo-level info
    if repo_root not in _git_repo_cache:
        repo_url = _run_git(["remote", "get-url", "origin"], cwd=repo_root)
        branch = _run_git(["branch", "--show-current"], cwd=repo_root)
        _git_repo_cache[repo_root] = {
            "git_repo": repo_url or repo_root,
            "git_branch": branch or "",
        }

    result = dict(_git_repo_cache[repo_root])

    # Per-file info: last commit hash and author
    log_output = _run_git(
        ["log", "-1", "--format=%H%n%an", "--", file_path],
        cwd=repo_root,
    )
    if log_output:
        lines = log_output.split("\n", 1)
        result["git_commit"] = lines[0]
        if len(lines) > 1:
            result["git_author"] = lines[1]

    return result


def collect_file_source(file_read: Dict[str, Any]) -> SourceRecord:
    """Build a SourceRecord from a FileManager pending_file_reads entry.

    Args:
        file_read: Dict with path, name, content, start_line, end_line, total_lines
    """
    file_path = file_read.get("path", "")
    checksum = file_read.get("checksum") or compute_file_checksum(file_path)
    git_meta = file_read.get("git_metadata") or collect_git_metadata(file_path)

    return SourceRecord(
        source_type="file",
        file_path=file_path,
        file_name=file_read.get("name", ""),
        line_start=file_read.get("start_line"),
        line_end=file_read.get("end_line"),
        checksum=checksum,
        git_repo=git_meta.get("git_repo"),
        git_branch=git_meta.get("git_branch"),
        git_commit=git_meta.get("git_commit"),
        git_author=git_meta.get("git_author"),
    )


def collect_conversation_source(
    session_id: Optional[str] = None,
    agent_id: Optional[str] = None,
) -> SourceRecord:
    """Build a SourceRecord for knowledge extracted from conversation."""
    return SourceRecord(
        source_type="conversation",
        session_id=session_id,
        agent_id=agent_id,
    )


def validate_checksum(source: SourceRecord) -> Optional[bool]:
    """Validate that a file source's checksum still matches.

    Returns:
        True if valid, False if changed, None if not a file source or file missing.
    """
    if source.source_type != "file" or not source.file_path or not source.checksum:
        return None

    current = compute_file_checksum(source.file_path)
    if current is None:
        return None  # File missing or unreadable

    return current == source.checksum
