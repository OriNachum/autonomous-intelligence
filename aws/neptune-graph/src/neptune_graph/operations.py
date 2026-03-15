"""Core graph operations: add, merge, split entities and relationships."""

import re
import uuid
from datetime import datetime, timezone
from typing import Any

from neptune_graph.client import NeptuneClient
from neptune_graph.exceptions import EntityNotFoundError


_VALID_IDENTIFIER = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


def _sanitize_label(label: str) -> str:
    """Sanitize a label/type for safe interpolation into openCypher.

    Only allows alphanumeric characters and underscores.
    """
    sanitized = re.sub(r"[^a-zA-Z0-9_]", "_", label)
    if not sanitized or sanitized[0].isdigit():
        sanitized = "N_" + sanitized
    return sanitized


def _validate_prop_key(key: str) -> None:
    """Validate that a property key is a safe openCypher identifier.

    Raises ValueError if the key contains characters that could cause
    Cypher injection or invalid queries.
    """
    if not _VALID_IDENTIFIER.match(key):
        raise ValueError(
            f"Invalid property key {key!r}: must match [A-Za-z_][A-Za-z0-9_]*"
        )


def _backtick_escape(key: str) -> str:
    """Backtick-escape a property key for safe use in openCypher.

    Backtick-escaping allows any key to be used safely as an identifier.
    Backticks within the key are escaped by doubling them.
    """
    return f"`{key.replace('`', '``')}`"


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _build_prop_set(prefix: str, properties: dict[str, Any], param_prefix: str = "p_") -> tuple[str, dict[str, Any]]:
    """Build SET clause fragments and parameter dict for user properties.

    Validates property keys against a strict identifier pattern before
    interpolating them into Cypher. Raises ValueError for invalid keys.

    Returns (set_clause_fragment, params_dict).
    """
    if not properties:
        return "", {}
    parts = []
    params = {}
    for key, value in properties.items():
        if key.startswith("_"):
            continue  # skip metadata keys from user properties
        _validate_prop_key(key)
        param_name = f"{param_prefix}{key}"
        parts.append(f"{prefix}.{_backtick_escape(key)} = ${param_name}")
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


def _relink_relationships(
    client: NeptuneClient,
    keep_name: str,
    remove_name: str,
    project: str,
    direction: str,
) -> None:
    """Re-link relationships from remove to keep, preserving original types.

    Since openCypher doesn't allow parameterized relationship types,
    we first query for distinct types, then re-create per type.
    """
    if direction == "outgoing":
        type_query = """
            MATCH (remove {name: $remove_name, `_project`: $project})-[r]->(target)
            MATCH (keep {name: $keep_name, `_project`: $project})
            WHERE target <> keep
            RETURN DISTINCT type(r) AS rtype
        """
    else:
        type_query = """
            MATCH (source)-[r]->(remove {name: $remove_name, `_project`: $project})
            MATCH (keep {name: $keep_name, `_project`: $project})
            WHERE source <> keep
            RETURN DISTINCT type(r) AS rtype
        """

    params = {
        "keep_name": keep_name,
        "remove_name": remove_name,
        "project": project,
    }

    types = client.execute(type_query, params)

    for row in types:
        rtype = row["rtype"]
        safe_type = _sanitize_label(rtype)

        if direction == "outgoing":
            relink_query = f"""
                MATCH (remove {{name: $remove_name, `_project`: $project}})-[r:{safe_type}]->(target)
                MATCH (keep {{name: $keep_name, `_project`: $project}})
                WHERE target <> keep
                WITH keep, target, properties(r) AS rprops, r
                DELETE r
                WITH keep, target, rprops
                CREATE (keep)-[r2:{safe_type}]->(target)
                SET r2 = rprops
                RETURN count(*) AS moved
            """
        else:
            relink_query = f"""
                MATCH (source)-[r:{safe_type}]->(remove {{name: $remove_name, `_project`: $project}})
                MATCH (keep {{name: $keep_name, `_project`: $project}})
                WHERE source <> keep
                WITH keep, source, properties(r) AS rprops, r
                DELETE r
                WITH keep, source, rprops
                CREATE (source)-[r2:{safe_type}]->(keep)
                SET r2 = rprops
                RETURN count(*) AS moved
            """

        client.execute(relink_query, params)


def merge_entities(
    client: NeptuneClient,
    keep_name: str,
    remove_name: str,
    strategy: str = "keep_primary",
) -> dict[str, Any]:
    """Merge two entities: keep one, transfer relationships, delete the other.

    3-step process:
    1. Copy properties from remove -> keep (based on strategy)
    2. Re-link all edges from remove -> keep (grouped by type)
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
        # Keep primary's properties; only fill in non-null values from
        # remove where keep has no value (null).
        prop_query = """
            MATCH (keep {name: $keep_name, `_project`: $project})
            MATCH (remove {name: $remove_name, `_project`: $project})
            WITH keep, remove, properties(remove) AS rprops, properties(keep) AS kprops
            SET keep.`_updated_at` = $now
            WITH keep, remove, rprops, kprops,
                 [k IN keys(rprops) WHERE NOT k STARTS WITH '_'
                  AND (NOT k IN keys(kprops) OR kprops[k] IS NULL)] AS fill_keys
            UNWIND CASE WHEN size(fill_keys) = 0 THEN [null] ELSE fill_keys END AS fk
            WITH keep, remove, rprops, fk
            WHERE fk IS NOT NULL
            CALL {
                WITH keep, rprops, fk
                WITH keep, rprops, fk
                SET keep += apoc.map.fromValues([fk, rprops[fk]])
            }
            RETURN keep.`_id` AS _id, keep.name AS name
        """
    else:
        # Overwrite: copy all non-metadata properties from remove onto keep
        prop_query = """
            MATCH (keep {name: $keep_name, `_project`: $project})
            MATCH (remove {name: $remove_name, `_project`: $project})
            WITH keep, remove, properties(remove) AS rprops
            SET keep.`_updated_at` = $now
            WITH keep, remove, rprops,
                 [k IN keys(rprops) WHERE NOT k STARTS WITH '_'] AS copy_keys
            UNWIND CASE WHEN size(copy_keys) = 0 THEN [null] ELSE copy_keys END AS ck
            WITH keep, remove, rprops, ck
            WHERE ck IS NOT NULL
            CALL {
                WITH keep, rprops, ck
                WITH keep, rprops, ck
                SET keep += apoc.map.fromValues([ck, rprops[ck]])
            }
            RETURN keep.`_id` AS _id, keep.name AS name
        """

    # Neptune Analytics may not support apoc — fall back to a simpler
    # approach that copies all non-metadata properties via SET += on the
    # full properties map, then restores metadata.
    if strategy == "keep_primary":
        # Only fill nulls: get remove props, filter to non-metadata,
        # then set only those where keep's value is null.
        # Since we can't conditionally SET per-key without APOC,
        # we do a read-then-write approach.
        remove_props_result = client.execute("""
            MATCH (remove {name: $remove_name, `_project`: $project})
            RETURN properties(remove) AS props
        """, {"remove_name": remove_name, "project": project})

        keep_props_result = client.execute("""
            MATCH (keep {name: $keep_name, `_project`: $project})
            RETURN properties(keep) AS props
        """, {"keep_name": keep_name, "project": project})

        if remove_props_result and keep_props_result:
            remove_props = remove_props_result[0]["props"]
            keep_props = keep_props_result[0]["props"]

            # Build SET for properties that are in remove but null/missing in keep
            fill_parts = []
            fill_params: dict[str, Any] = {
                "keep_name": keep_name,
                "project": project,
                "now": now,
            }
            idx = 0
            for k, v in remove_props.items():
                if k.startswith("_"):
                    continue
                if k not in keep_props or keep_props[k] is None:
                    _validate_prop_key(k)
                    param = f"fill_{idx}"
                    fill_parts.append(f"keep.{_backtick_escape(k)} = ${param}")
                    fill_params[param] = v
                    idx += 1

            set_clause = ", ".join(fill_parts)
            if set_clause:
                set_clause = ", " + set_clause
            client.execute(f"""
                MATCH (keep {{name: $keep_name, `_project`: $project}})
                SET keep.`_updated_at` = $now{set_clause}
                RETURN keep.`_id` AS _id
            """, fill_params)
        else:
            client.execute("""
                MATCH (keep {name: $keep_name, `_project`: $project})
                SET keep.`_updated_at` = $now
                RETURN keep.`_id` AS _id
            """, {"keep_name": keep_name, "project": project, "now": now})
    else:
        # Overwrite: copy all non-metadata properties from remove onto keep
        remove_props_result = client.execute("""
            MATCH (remove {name: $remove_name, `_project`: $project})
            RETURN properties(remove) AS props
        """, {"remove_name": remove_name, "project": project})

        copy_parts = []
        copy_params: dict[str, Any] = {
            "keep_name": keep_name,
            "project": project,
            "now": now,
        }
        if remove_props_result:
            remove_props = remove_props_result[0]["props"]
            idx = 0
            for k, v in remove_props.items():
                if k.startswith("_"):
                    continue
                _validate_prop_key(k)
                param = f"copy_{idx}"
                copy_parts.append(f"keep.{_backtick_escape(k)} = ${param}")
                copy_params[param] = v
                idx += 1

        set_clause = ", ".join(copy_parts)
        if set_clause:
            set_clause = ", " + set_clause
        client.execute(f"""
            MATCH (keep {{name: $keep_name, `_project`: $project}})
            SET keep.`_updated_at` = $now{set_clause}
            RETURN keep.`_id` AS _id
        """, copy_params)

    # Step 2: Re-link relationships preserving original types
    _relink_relationships(client, keep_name, remove_name, project, "outgoing")
    _relink_relationships(client, keep_name, remove_name, project, "incoming")

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
    2. Copy specified properties from source -> new, remove from source
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

    # Step 2: Move properties using backtick-escaped access
    if move_properties:
        for prop in move_properties:
            escaped = _backtick_escape(prop)
            client.execute(f"""
                MATCH (source {{name: $source_name, `_project`: $project}})
                MATCH (target {{name: $new_name, `_project`: $project}})
                SET target.{escaped} = source.{escaped}
                REMOVE source.{escaped}
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
