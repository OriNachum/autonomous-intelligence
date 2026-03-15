"""Configuration for Neptune Graph connections."""

import json
import os
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class NeptuneGraphConfig:
    """Configuration for connecting to a Neptune Analytics graph."""

    graph_id: str = ""
    region: str = "us-east-1"
    project: str = ""
    source: str = "manual"

    def __post_init__(self):
        self.graph_id = self.graph_id or os.getenv("NEPTUNE_GRAPH_ID", "")
        self.region = self.region or os.getenv("NEPTUNE_REGION", "us-east-1")
        self.project = self.project or os.getenv("NEPTUNE_PROJECT", "")
        self.source = self.source or os.getenv("NEPTUNE_SOURCE", "manual")

    @classmethod
    def from_file(cls, path: str | Path) -> "NeptuneGraphConfig":
        """Load config from a JSON file with env-var overrides."""
        with open(path) as f:
            data = json.load(f)

        neptune = data.get("neptune", {})
        defaults = data.get("defaults", {})

        return cls(
            graph_id=neptune.get("graph_identifier", ""),
            region=neptune.get("region", "us-east-1"),
            project=defaults.get("project", ""),
            source=defaults.get("source", "manual"),
        )

    @property
    def endpoint(self) -> str:
        """Full Neptune Analytics endpoint URL."""
        return f"https://{self.graph_id}.{self.region}.neptune-graph.amazonaws.com"
