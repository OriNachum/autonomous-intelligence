"""Core graph operations: add, merge, split entities and relationships."""

import re
import uuid
from datetime import datetime, timezone
from typing import Any

from neptune_graph.client import NeptuneClient
from neptune_graph.exceptions import EntityNotFoundError, QueryError


def _sanitize_label(label: str) -> str:
    """Sanitize a label/type for safe interpolation into openCypher.

    Only allows alphanumeric characters and underscores.
    """
    sanitized = re.sub(r"[^a-zA-Z0-9_]", "_", label)
    if not sanitized or sanitized[0].isdigit():
        sanitized = "N_" + sanitized
    return sanitized


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _build_prop_set(prefix: str, properties: dict[str, Any], param_prefix: str = "p_") -> tuple[str, dict[str, Any]]:
    """Build SET clause fragments and parameter dict for user properties.

    Returns (set_clause_fragment, params_dict).
    """
    if not properties:
        return "", {}
    parts = []
    params = {}
    for key, value in properties.items():
        if key.startswith("_"):
            continue  # skip metadata keys from user properties
        param_name = f"{param_prefix}{key}"
        parts.append(f"{prefix}.{key} = ${param_name}")
        params[param_name] = value
    return ", ".join(parts), params


def add_entity(
    client: NeptuneClient,
    label: str,
    name: str,
    properties: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Add or update an entity node.

    Uses find_or_create pattern: searches by name + _project first,
    then MERGE on _id.
    """
    safe_label = _sanitize_label(label)
    project = client.config.project
    source = client.config.source
    now = _now_iso()
    properties = properties or {}

    # Search for existing entity by name + project
    find_query = f"""
        MATCH (n:{safe_label} {{name: $name, `_project`: $project}})
        RETURN n.`_id` AS _id, n.name AS name
    """
    existing = client.execute(find_query, {"name": name, "project": project})

    if existing:
        entity_id = existing[0]["_id"]
    else:
        entity_id = str(uuid.uuid4())

    # Build user property SET
    prop_set, prop_params = _build_prop_set("n", properties)
    prop_set_clause = f", {prop_set}" if prop_set else ""

    query = f"""
        MERGE (n:{safe_label} {{`_id`: $entity_id, `_project`: $project}})
        ON CREATE SET
            n.name = $name,
            n.`_created_at` = $now,
            n.`_updated_at` = $now,
            n.`_source` = $source{prop_set_clause}
        ON MATCH SET
            n.name = $name,
            n.`_updated_at` = $now{prop_set_clause}
        RETURN n.`_id` AS _id, n.name AS name
    """

    params = {
        "entity_id": entity_id,
        "project": project,
        "name": name,
        "now": now,
        "source": source,
        **prop_params,
    }

    result = client.execute(query, params)
    return result[0] if result else {"_id": entity_id, "name": name}


def add_relationship(
    client: NeptuneClient,
    from_name: str,
    to_name: str,
    rel_type: str,
    properties: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Add or update a relationship between two entities.

    Matches entities by name + _project, then MERGE the edge.
    """
    safe_type = _sanitize_label(rel_type)
    project = client.config.project
    source = client.config.source
    now = _now_iso()
    properties = properties or {}

    prop_set, prop_params = _build_prop_set("r", properties)
    prop_set_clause = f", {prop_set}" if prop_set else ""

    query = f"""
        MATCH (a {{name: $from_name, `_project`: $project}})
        MATCH (b {{name: $to_name, `_project`: $project}})
        MERGE (a)-[r:{safe_type}]->(b)
        ON CREATE SET
            r.`_project` = $project,
            r.`_created_at` = $now,
            r.`_updated_at` = $now,
            r.`_source` = $source{prop_set_clause}
        ON MATCH SET
            r.`_updated_at` = $now{prop_set_clause}
        RETURN type(r) AS rel_type, a.name AS from_name, b.name AS to_name
    """

    params = {
        "from_name": from_name,
        "to_name": to_name,
        "project": project,
        "now": now,
        "source": source,
        **prop_params,
    }

    result = client.execute(query, params)
    if not result:
        raise EntityNotFoundError(f"{from_name} or {to_name}")
    return result[0]


def add_self_relationship(
    client: NeptuneClient,
    entity_name: str,
    rel_type: str,
    properties: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Add a self-relationship (annotation/note) on an entity.

    Uses CREATE (not MERGE) so multiple annotations are allowed.
    """
    safe_type = _sanitize_label(rel_type)
    project = client.config.project
    source = client.config.source
    now = _now_iso()
    properties = properties or {}

    prop_set, prop_params = _build_prop_set("r", properties)
    prop_set_clause = f", {prop_set}" if prop_set else ""

    query = f"""
        MATCH (n {{name: $entity_name, `_project`: $project}})
        CREATE (n)-[r:{safe_type}]->(n)
        SET r.`_project` = $project,
            r.`_created_at` = $now,
            r.`_updated_at` = $now,
            r.`_source` = $source{prop_set_clause}
        RETURN type(r) AS rel_type, n.name AS entity_name
    """

    params = {
        "entity_name": entity_name,
        "project": project,
        "now": now,
        "source": source,
        **prop_params,
    }

    result = client.execute(query, params)
    if not result:
        raise EntityNotFoundError(entity_name)
    return result[0]


def merge_entities(
    client: NeptuneClient,
    keep_name: str,
    remove_name: str,
    strategy: str = "keep_primary",
) -> dict[str, Any]:
    """Merge two entities: keep one, transfer relationships, delete the other.

    3-step process:
    1. Copy properties from remove → keep (based on strategy)
    2. Re-link all edges from remove → keep (grouped by type)
    3. DETACH DELETE the removed entity
    """
    project = client.config.project
    now = _now_iso()

    # Verify both exist
    for name in [keep_name, remove_name]:
        check = client.execute(
            "MATCH (n {name: $name, `_project`: $project}) RETURN n.`_id` AS _id",
            {"name": name, "project": project},
        )
        if not check:
            raise EntityNotFoundError(name)

    # Step 1: Merge properties
    if strategy == "keep_primary":
        # Keep canonical's properties, only fill in nulls from secondary
        prop_query = """
            MATCH (keep {name: $keep_name, `_project`: $project})
            MATCH (remove {name: $remove_name, `_project`: $project})
            SET keep.`_updated_at` = $now
            RETURN keep.`_id` AS _id, keep.name AS name
        """
    else:
        prop_query = """
            MATCH (keep {name: $keep_name, `_project`: $project})
            MATCH (remove {name: $remove_name, `_project`: $project})
            SET keep.`_updated_at` = $now
            RETURN keep.`_id` AS _id, keep.name AS name
        """

    client.execute(prop_query, {
        "keep_name": keep_name,
        "remove_name": remove_name,
        "project": project,
        "now": now,
    })

    # Step 2: Re-link outgoing relationships
    client.execute("""
        MATCH (remove {name: $remove_name, `_project`: $project})-[r]->(target)
        MATCH (keep {name: $keep_name, `_project`: $project})
        WHERE target <> keep
        WITH keep, target, type(r) AS rtype, properties(r) AS rprops, r
        DELETE r
        WITH keep, target, rtype, rprops
        CALL {
            WITH keep, target, rprops
            CREATE (keep)-[r2:TRANSFERRED]->(target)
            SET r2 = rprops
            RETURN r2
        }
        RETURN count(*) AS moved
    """, {
        "keep_name": keep_name,
        "remove_name": remove_name,
        "project": project,
    })

    # Step 2b: Re-link incoming relationships
    client.execute("""
        MATCH (source)-[r]->(remove {name: $remove_name, `_project`: $project})
        MATCH (keep {name: $keep_name, `_project`: $project})
        WHERE source <> keep
        WITH keep, source, type(r) AS rtype, properties(r) AS rprops, r
        DELETE r
        WITH keep, source, rtype, rprops
        CALL {
            WITH keep, source, rprops
            CREATE (source)-[r2:TRANSFERRED]->(keep)
            SET r2 = rprops
            RETURN r2
        }
        RETURN count(*) AS moved
    """, {
        "keep_name": keep_name,
        "remove_name": remove_name,
        "project": project,
    })

    # Step 3: Delete the removed entity
    client.execute(
        "MATCH (n {name: $remove_name, `_project`: $project}) DETACH DELETE n",
        {"remove_name": remove_name, "project": project},
    )

    return {"kept": keep_name, "removed": remove_name, "status": "merged"}


def split_entity(
    client: NeptuneClient,
    source_name: str,
    new_label: str,
    new_name: str,
    move_properties: list[str] | None = None,
    move_rel_types: list[str] | None = None,
) -> dict[str, Any]:
    """Split an entity: create a new entity and move specified properties/relationships.

    3-step process:
    1. Create new entity
    2. Copy specified properties from source → new, remove from source
    3. Re-link specified relationship types to new entity
    """
    project = client.config.project
    move_properties = move_properties or []
    move_rel_types = move_rel_types or []

    # Verify source exists
    check = client.execute(
        "MATCH (n {name: $name, `_project`: $project}) RETURN n.`_id` AS _id",
        {"name": source_name, "project": project},
    )
    if not check:
        raise EntityNotFoundError(source_name)

    # Step 1: Create new entity
    new_entity = add_entity(client, new_label, new_name)

    # Step 2: Move properties
    if move_properties:
        for prop in move_properties:
            safe_prop = re.sub(r"[^a-zA-Z0-9_]", "_", prop)
            client.execute(f"""
                MATCH (source {{name: $source_name, `_project`: $project}})
                MATCH (target {{name: $new_name, `_project`: $project}})
                SET target.{safe_prop} = source.{safe_prop}
                REMOVE source.{safe_prop}
            """, {
                "source_name": source_name,
                "new_name": new_name,
                "project": project,
            })

    # Step 3: Re-link specified relationship types
    for rel_type in move_rel_types:
        safe_type = _sanitize_label(rel_type)
        # Move outgoing
        client.execute(f"""
            MATCH (source {{name: $source_name, `_project`: $project}})-[r:{safe_type}]->(target)
            MATCH (new {{name: $new_name, `_project`: $project}})
            WHERE target <> new
            CREATE (new)-[r2:{safe_type}]->(target)
            SET r2 = properties(r)
            DELETE r
        """, {
            "source_name": source_name,
            "new_name": new_name,
            "project": project,
        })
        # Move incoming
        client.execute(f"""
            MATCH (origin)-[r:{safe_type}]->(source {{name: $source_name, `_project`: $project}})
            MATCH (new {{name: $new_name, `_project`: $project}})
            WHERE origin <> new
            CREATE (origin)-[r2:{safe_type}]->(new)
            SET r2 = properties(r)
            DELETE r
        """, {
            "source_name": source_name,
            "new_name": new_name,
            "project": project,
        })

    return {
        "source": source_name,
        "new_entity": new_entity,
        "moved_properties": move_properties,
        "moved_rel_types": move_rel_types,
        "status": "split",
    }
