"""Query operations: search, get, summary."""

from typing import Any

from neptune_graph.client import NeptuneClient
from neptune_graph.exceptions import EntityNotFoundError
from neptune_graph.operations import _sanitize_label


def search_entities(
    client: NeptuneClient,
    query: str,
    label: str | None = None,
    limit: int = 20,
) -> list[dict[str, Any]]:
    """Search entities by name (case-insensitive CONTAINS).

    Args:
        client: NeptuneClient instance.
        query: Search string to match against entity names.
        label: Optional label filter.
        limit: Maximum results.
    """
    project = client.config.project

    if label:
        safe_label = _sanitize_label(label)
        cypher = f"""
            MATCH (n:{safe_label} {{`_project`: $project}})
            WHERE toLower(n.name) CONTAINS toLower($query)
            RETURN n.`_id` AS _id, n.name AS name, labels(n)[0] AS label,
                   n.`_created_at` AS _created_at, n.`_updated_at` AS _updated_at
            ORDER BY n.name
            LIMIT $limit
        """
    else:
        cypher = """
            MATCH (n {`_project`: $project})
            WHERE toLower(n.name) CONTAINS toLower($query)
            RETURN n.`_id` AS _id, n.name AS name, labels(n)[0] AS label,
                   n.`_created_at` AS _created_at, n.`_updated_at` AS _updated_at
            ORDER BY n.name
            LIMIT $limit
        """

    return client.execute(cypher, {"project": project, "query": query, "limit": limit})


def get_entity(
    client: NeptuneClient,
    name: str,
) -> dict[str, Any]:
    """Get a single entity by exact name match.

    Raises EntityNotFoundError if not found.
    """
    project = client.config.project

    result = client.execute("""
        MATCH (n {name: $name, `_project`: $project})
        RETURN n.`_id` AS _id, n.name AS name, labels(n)[0] AS label,
               n.`_created_at` AS _created_at, n.`_updated_at` AS _updated_at,
               n.`_source` AS _source, properties(n) AS properties
    """, {"name": name, "project": project})

    if not result:
        raise EntityNotFoundError(name)
    return result[0]


def get_relationships(
    client: NeptuneClient,
    name: str,
    direction: str = "both",
) -> list[dict[str, Any]]:
    """Get relationships for an entity.

    Args:
        client: NeptuneClient instance.
        name: Entity name.
        direction: "both", "in", or "out".
    """
    project = client.config.project

    if direction == "out":
        cypher = """
            MATCH (n {name: $name, `_project`: $project})-[r]->(target)
            RETURN type(r) AS rel_type, n.name AS from_name, target.name AS to_name,
                   properties(r) AS properties, 'out' AS direction
        """
    elif direction == "in":
        cypher = """
            MATCH (source)-[r]->(n {name: $name, `_project`: $project})
            RETURN type(r) AS rel_type, source.name AS from_name, n.name AS to_name,
                   properties(r) AS properties, 'in' AS direction
        """
    else:
        cypher = """
            MATCH (n {name: $name, `_project`: $project})-[r]->(target)
            RETURN type(r) AS rel_type, n.name AS from_name, target.name AS to_name,
                   properties(r) AS properties, 'out' AS direction
            UNION ALL
            MATCH (source)-[r]->(n {name: $name, `_project`: $project})
            WHERE source <> n
            RETURN type(r) AS rel_type, source.name AS from_name, n.name AS to_name,
                   properties(r) AS properties, 'in' AS direction
        """

    return client.execute(cypher, {"name": name, "project": project})


def get_summary(client: NeptuneClient) -> dict[str, Any]:
    """Get a summary of the graph for the current project."""
    project = client.config.project

    # Entity counts by label
    label_results = client.execute("""
        MATCH (n {`_project`: $project})
        RETURN labels(n)[0] AS label, count(n) AS count
    """, {"project": project})

    # Relationship counts by type
    rel_results = client.execute("""
        MATCH (a {`_project`: $project})-[r]->(b)
        RETURN type(r) AS rel_type, count(r) AS count
    """, {"project": project})

    entity_counts = {r["label"]: r["count"] for r in label_results if r.get("label")}
    rel_counts = {r["rel_type"]: r["count"] for r in rel_results if r.get("rel_type")}

    return {
        "project": project,
        "total_entities": sum(entity_counts.values()),
        "total_relationships": sum(rel_counts.values()),
        "entity_counts": entity_counts,
        "relationship_counts": rel_counts,
    }
