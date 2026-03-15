"""Boto3 wrapper for Neptune Analytics graph queries."""

import json
from typing import Any

import boto3

from neptune_graph.config import NeptuneGraphConfig
from neptune_graph.exceptions import NeptuneGraphError, QueryError


class NeptuneClient:
    """Execute openCypher queries against a Neptune Analytics graph."""

    def __init__(self, config: NeptuneGraphConfig | None = None):
        self.config = config or NeptuneGraphConfig()
        if not self.config.graph_id:
            raise NeptuneGraphError("graph_id is required — set NEPTUNE_GRAPH_ID or pass config")
        self._client = boto3.client(
            "neptune-graph",
            region_name=self.config.region,
        )

    def execute(
        self,
        query: str,
        parameters: dict[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        """Execute an openCypher query and return results.

        Args:
            query: openCypher query string.
            parameters: Query parameters (values only — labels are interpolated).

        Returns:
            List of result records as dicts.
        """
        try:
            kwargs: dict[str, Any] = {
                "graphIdentifier": self.config.graph_id,
                "queryString": query,
                "language": "OPEN_CYPHER",
            }
            if parameters:
                kwargs["parameters"] = json.dumps(parameters)

            response = self._client.execute_query(**kwargs)
            payload = json.loads(response["payload"].read())
            return payload.get("results", [])
        except self._client.exceptions.ConflictException as e:
            raise QueryError(str(e), query) from e
        except self._client.exceptions.ValidationException as e:
            raise QueryError(str(e), query) from e
        except Exception as e:
            if "neptune" in type(e).__module__.lower() if hasattr(type(e), "__module__") else False:
                raise QueryError(str(e), query) from e
            raise NeptuneGraphError(str(e)) from e

    def check(self) -> dict[str, Any]:
        """Health check — verify connectivity to the graph."""
        try:
            result = self._client.get_graph(graphIdentifier=self.config.graph_id)
            return {
                "status": "connected",
                "graph_id": self.config.graph_id,
                "region": self.config.region,
                "graph_status": result.get("status", "unknown"),
                "endpoint": result.get("endpoint", ""),
            }
        except Exception as e:
            return {
                "status": "unavailable",
                "graph_id": self.config.graph_id,
                "region": self.config.region,
                "error": str(e),
            }
