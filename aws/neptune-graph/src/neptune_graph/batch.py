"""Batch operations using UNWIND for efficient bulk inserts."""

import uuid
from collections import defaultdict
from datetime import datetime, timezone
from typing import Any

from neptune_graph.client import NeptuneClient
from neptune_graph.operations import _sanitize_label


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def batch_add_entities(
    client: NeptuneClient,
    items: list[dict[str, Any]],
) -> dict[str, Any]:
    """Batch add entities, grouped by label for efficient UNWIND queries.

    Each item should have: label, name, and optionally properties.

    Returns summary of created/updated counts per label.
    """
    project = client.config.project
    source = client.config.source
    now = _now_iso()

    # Group by label
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for item in items:
        label = item.get("label", "Entity")
        grouped[label].append(item)

    results: dict[str, int] = {}

    for label, group in grouped.items():
        safe_label = _sanitize_label(label)

        # Build batch data
        batch_data = []
        for item in group:
            entry: dict[str, Any] = {
                "_id": str(uuid.uuid4()),
                "name": item["name"],
                "_project": project,
                "_created_at": now,
                "_updated_at": now,
                "_source": source,
            }
            for k, v in item.get("properties", {}).items():
                if not k.startswith("_"):
                    entry[k] = v
            batch_data.append(entry)

        # Collect all property keys across the batch
        all_keys = set()
        for entry in batch_data:
            all_keys.update(entry.keys())
        all_keys -= {"_id", "name", "_project", "_created_at", "_updated_at", "_source"}

        extra_set = ""
        if all_keys:
            extra_parts = [f"n.{k} = item.{k}" for k in sorted(all_keys)]
            extra_set = ", " + ", ".join(extra_parts)

        query = f"""
            UNWIND $batch AS item
            MERGE (n:{safe_label} {{name: item.name, `_project`: item._project}})
            ON CREATE SET
                n.`_id` = item._id,
                n.`_created_at` = item._created_at,
                n.`_updated_at` = item._updated_at,
                n.`_source` = item._source{extra_set}
            ON MATCH SET
                n.`_updated_at` = item._updated_at{extra_set}
            RETURN count(n) AS count
        """

        result = client.execute(query, {"batch": batch_data})
        results[label] = result[0]["count"] if result else 0

    return {"entities_processed": results, "total": sum(results.values())}


def batch_add_relationships(
    client: NeptuneClient,
    items: list[dict[str, Any]],
) -> dict[str, Any]:
    """Batch add relationships, grouped by type for efficient UNWIND queries.

    Each item should have: from_name, to_name, rel_type, and optionally properties.

    Returns summary of created/updated counts per relationship type.
    """
    project = client.config.project
    source = client.config.source
    now = _now_iso()

    # Group by rel_type
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for item in items:
        rel_type = item.get("rel_type", "RELATES_TO")
        grouped[rel_type].append(item)

    results: dict[str, int] = {}

    for rel_type, group in grouped.items():
        safe_type = _sanitize_label(rel_type)

        batch_data = []
        for item in group:
            entry: dict[str, Any] = {
                "from_name": item["from_name"],
                "to_name": item["to_name"],
                "_project": project,
                "_created_at": now,
                "_updated_at": now,
                "_source": source,
            }
            for k, v in item.get("properties", {}).items():
                if not k.startswith("_"):
                    entry[k] = v
            batch_data.append(entry)

        # Collect extra property keys
        all_keys = set()
        for entry in batch_data:
            all_keys.update(entry.keys())
        all_keys -= {"from_name", "to_name", "_project", "_created_at", "_updated_at", "_source"}

        extra_set = ""
        if all_keys:
            extra_parts = [f"r.{k} = item.{k}" for k in sorted(all_keys)]
            extra_set = ", " + ", ".join(extra_parts)

        query = f"""
            UNWIND $batch AS item
            MATCH (a {{name: item.from_name, `_project`: item._project}})
            MATCH (b {{name: item.to_name, `_project`: item._project}})
            MERGE (a)-[r:{safe_type}]->(b)
            ON CREATE SET
                r.`_project` = item._project,
                r.`_created_at` = item._created_at,
                r.`_updated_at` = item._updated_at,
                r.`_source` = item._source{extra_set}
            ON MATCH SET
                r.`_updated_at` = item._updated_at{extra_set}
            RETURN count(r) AS count
        """

        result = client.execute(query, {"batch": batch_data})
        results[rel_type] = result[0]["count"] if result else 0

    return {"relationships_processed": results, "total": sum(results.values())}
