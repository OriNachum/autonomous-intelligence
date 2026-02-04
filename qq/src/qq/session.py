"""Session management for parallel QQ execution.

Each QQ instance runs with a unique session ID, isolating mutable state
(history, file manager state) to prevent race conditions in parallel execution.
"""

import os
import uuid
from datetime import datetime
from pathlib import Path
from typing import Optional

_current_session_id: Optional[str] = None


def generate_session_id() -> str:
    """Generate unique session ID.

    Format: YYYYMMDD_HHMMSS_<8-char-uuid>
    Example: 20240115_143052_a1b2c3d4
    """
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    short_uuid = uuid.uuid4().hex[:8]
    return f"{timestamp}_{short_uuid}"


def get_session_id() -> str:
    """Get current session ID, generating if needed.

    The session ID is cached for the lifetime of the process.
    Can also be set via QQ_SESSION_ID environment variable.
    """
    global _current_session_id
    if _current_session_id is None:
        # Check environment variable first (for external control)
        env_session = os.environ.get("QQ_SESSION_ID")
        if env_session:
            _current_session_id = env_session
        else:
            _current_session_id = generate_session_id()
    return _current_session_id


def set_session_id(session_id: str) -> None:
    """Set session ID explicitly (for resuming sessions).

    Args:
        session_id: The session ID to use
    """
    global _current_session_id
    _current_session_id = session_id


def get_session_dir(base_dir: Path, agent_name: str) -> Path:
    """Get session-specific directory for an agent.

    Creates the directory structure:
    <base_dir>/<agent_name>/sessions/<session_id>/

    Args:
        base_dir: Base directory (typically ~/.qq)
        agent_name: Name of the agent

    Returns:
        Path to the session directory (created if needed)
    """
    session_dir = base_dir / agent_name / "sessions" / get_session_id()
    session_dir.mkdir(parents=True, exist_ok=True)
    return session_dir


def list_sessions(base_dir: Path, agent_name: str) -> list[str]:
    """List all session IDs for an agent.

    Args:
        base_dir: Base directory (typically ~/.qq)
        agent_name: Name of the agent

    Returns:
        List of session IDs, sorted by creation time (newest first)
    """
    sessions_dir = base_dir / agent_name / "sessions"
    if not sessions_dir.exists():
        return []

    sessions = []
    for item in sessions_dir.iterdir():
        if item.is_dir() and not item.name.startswith("."):
            sessions.append(item.name)

    # Sort by timestamp (session ID starts with YYYYMMDD_HHMMSS)
    return sorted(sessions, reverse=True)


def get_latest_session(base_dir: Path, agent_name: str) -> Optional[str]:
    """Get the most recent session ID for an agent.

    Args:
        base_dir: Base directory (typically ~/.qq)
        agent_name: Name of the agent

    Returns:
        Most recent session ID, or None if no sessions exist
    """
    sessions = list_sessions(base_dir, agent_name)
    return sessions[0] if sessions else None
