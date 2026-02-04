"""Backup manifest and metadata handling."""

import json
from dataclasses import dataclass, field, asdict
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, Optional, List


FORMAT_VERSION = "2"


@dataclass
class BackupInfo:
    """Summary information about a backup for listing."""

    backup_id: str
    created_at: datetime
    trigger: str
    notes_success: bool
    mongodb_success: bool
    neo4j_success: bool
    notes_count: Optional[int] = None
    mongodb_count: Optional[int] = None
    neo4j_nodes: Optional[int] = None
    neo4j_rels: Optional[int] = None

    @property
    def is_complete(self) -> bool:
        """Check if all stores were backed up successfully."""
        return self.notes_success and self.mongodb_success and self.neo4j_success


@dataclass
class BackupManifest:
    """Backup metadata stored in manifest.json."""

    backup_id: str
    created_at: datetime
    trigger: str  # "daily" | "manual" | "scheduled"

    notes: Dict[str, Any] = field(default_factory=dict)
    mongodb: Dict[str, Any] = field(default_factory=dict)
    neo4j: Dict[str, Any] = field(default_factory=dict)

    format_version: str = FORMAT_VERSION
    qq_version: str = "0.1.0"

    def to_json(self) -> str:
        """Serialize to JSON string."""
        data = asdict(self)
        # Convert datetime to ISO format
        data["created_at"] = self.created_at.isoformat()
        return json.dumps(data, indent=2)

    def save(self, backup_path: Path) -> None:
        """Save manifest to backup directory."""
        manifest_file = backup_path / "manifest.json"
        manifest_file.write_text(self.to_json())

    @classmethod
    def from_json(cls, data: str) -> "BackupManifest":
        """Deserialize from JSON string."""
        parsed = json.loads(data)
        # Convert ISO string back to datetime
        parsed["created_at"] = datetime.fromisoformat(parsed["created_at"])
        return cls(**parsed)

    @classmethod
    def load(cls, backup_path: Path) -> "BackupManifest":
        """Load manifest from backup directory."""
        manifest_file = backup_path / "manifest.json"
        return cls.from_json(manifest_file.read_text())

    def to_info(self) -> BackupInfo:
        """Convert to BackupInfo for listing."""
        return BackupInfo(
            backup_id=self.backup_id,
            created_at=self.created_at,
            trigger=self.trigger,
            notes_success=self.notes.get("success", False),
            mongodb_success=self.mongodb.get("success", False),
            neo4j_success=self.neo4j.get("success", False),
            notes_count=self.notes.get("size_bytes"),
            mongodb_count=self.mongodb.get("count"),
            neo4j_nodes=self.neo4j.get("nodes"),
            neo4j_rels=self.neo4j.get("rels"),
        )

    @property
    def is_complete(self) -> bool:
        """Check if all stores were backed up successfully."""
        return (
            self.notes.get("success", False)
            and self.mongodb.get("success", False)
            and self.neo4j.get("success", False)
        )

    def summary(self) -> str:
        """Get human-readable summary of backup."""
        lines = [
            f"Backup: {self.backup_id}",
            f"Created: {self.created_at.strftime('%Y-%m-%d %H:%M:%S')}",
            f"Trigger: {self.trigger}",
            "",
            "Stores:",
        ]

        # Notes
        if self.notes.get("success"):
            size = self.notes.get("size_bytes", 0)
            lines.append(f"  notes.md: {size:,} bytes")
        else:
            lines.append(f"  notes.md: FAILED - {self.notes.get('error', 'unknown')}")

        # MongoDB
        if self.mongodb.get("success"):
            count = self.mongodb.get("count", 0)
            lines.append(f"  MongoDB: {count:,} notes")
        else:
            lines.append(f"  MongoDB: FAILED - {self.mongodb.get('error', 'unknown')}")

        # Neo4j
        if self.neo4j.get("success"):
            nodes = self.neo4j.get("nodes", 0)
            rels = self.neo4j.get("rels", 0)
            lines.append(f"  Neo4j: {nodes:,} nodes, {rels:,} relationships")
        else:
            lines.append(f"  Neo4j: FAILED - {self.neo4j.get('error', 'unknown')}")

        return "\n".join(lines)
