"""Backup functions for individual memory stores.

Each function streams data to JSONL format for scalability.
Embeddings are excluded - they can be regenerated on restore.
"""

import json
import os
from pathlib import Path
from typing import Dict, Any


def backup_notes(backup_path: Path) -> Dict[str, Any]:
    """
    Backup notes.md file.

    Args:
        backup_path: Directory to write backup files

    Returns:
        {"success": True, "file": "notes.md", "size_bytes": 1234}
    """
    from qq.memory.notes import NotesManager

    try:
        manager = NotesManager()
        content = manager.get_notes()

        dest = backup_path / "notes.md"
        dest.write_text(content)

        return {
            "success": True,
            "file": "notes.md",
            "size_bytes": len(content.encode("utf-8")),
        }
    except Exception as e:
        return {"success": False, "error": str(e)}


def backup_mongodb(backup_path: Path) -> Dict[str, Any]:
    """
    Export MongoDB notes collection to JSONL (streaming format).

    - Excludes embeddings (regenerable from content)
    - Writes one document per line (no full collection in memory)
    - Preserves: note_id, content, section, metadata, updated_at

    Args:
        backup_path: Directory to write backup files

    Returns:
        {"success": True, "file": "mongodb_notes.jsonl", "count": 42, "embeddings_excluded": True}
    """
    from pymongo import MongoClient
    from pymongo.errors import ConnectionFailure, ServerSelectionTimeoutError

    uri = os.getenv("MONGODB_URI", "mongodb://localhost:27017")

    try:
        client = MongoClient(uri, serverSelectionTimeoutMS=5000)
        # Test connection
        client.admin.command("ping")

        db = client["qq_memory"]
        dest = backup_path / "mongodb_notes.jsonl"
        count = 0

        # Stream write - never load full collection into memory
        with open(dest, "w") as f:
            # Exclude embedding field in projection
            for doc in db["notes"].find({}, {"embedding": 0}):
                record = {
                    "note_id": doc.get("note_id"),
                    "content": doc.get("content"),
                    "section": doc.get("section"),
                    "metadata": doc.get("metadata", {}),
                    "updated_at": (
                        doc["updated_at"].isoformat() if doc.get("updated_at") else None
                    ),
                }
                f.write(json.dumps(record) + "\n")
                count += 1

        client.close()

        return {
            "success": True,
            "file": "mongodb_notes.jsonl",
            "count": count,
            "embeddings_excluded": True,
        }

    except (ConnectionFailure, ServerSelectionTimeoutError) as e:
        return {"success": False, "error": f"MongoDB connection failed: {e}"}
    except Exception as e:
        return {"success": False, "error": str(e)}


def backup_neo4j(backup_path: Path) -> Dict[str, Any]:
    """
    Export Neo4j graph to JSONL (streaming format).

    - Excludes embeddings (regenerable from name + description)
    - Writes nodes first, then relationships
    - Each line is self-contained record with _type marker

    Args:
        backup_path: Directory to write backup files

    Returns:
        {"success": True, "file": "neo4j_graph.jsonl", "nodes": 10, "rels": 5, "embeddings_excluded": True}
    """
    from neo4j import GraphDatabase
    from neo4j.exceptions import ServiceUnavailable, AuthError

    uri = os.getenv("NEO4J_URI", "bolt://localhost:7687")
    user = os.getenv("NEO4J_USER", "neo4j")
    password = os.getenv("NEO4J_PASSWORD", "refinerypass")

    try:
        driver = GraphDatabase.driver(uri, auth=(user, password))
        # Test connection
        driver.verify_connectivity()

        dest = backup_path / "neo4j_graph.jsonl"
        node_count = 0
        rel_count = 0

        with open(dest, "w") as f:
            with driver.session() as session:
                # Stream nodes
                result = session.run(
                    """
                    MATCH (n)
                    RETURN labels(n) as labels, properties(n) as props
                    """
                )
                for record in result:
                    props = dict(record["props"])
                    # Exclude embedding - will regenerate on restore
                    node_record = {
                        "_type": "node",
                        "labels": list(record["labels"]),
                        "name": props.get("name"),
                        "description": props.get("description"),
                        # Include other properties except embedding
                        "properties": {
                            k: v
                            for k, v in props.items()
                            if k not in ("embedding", "name", "description")
                        },
                    }
                    f.write(json.dumps(node_record) + "\n")
                    node_count += 1

                # Stream relationships
                result = session.run(
                    """
                    MATCH (a)-[r]->(b)
                    RETURN a.name as source, b.name as target,
                           type(r) as rel_type, properties(r) as props
                    """
                )
                for record in result:
                    rel_record = {
                        "_type": "relationship",
                        "source": record["source"],
                        "target": record["target"],
                        "rel_type": record["rel_type"],
                        "properties": dict(record["props"]) if record["props"] else {},
                    }
                    f.write(json.dumps(rel_record) + "\n")
                    rel_count += 1

        driver.close()

        return {
            "success": True,
            "file": "neo4j_graph.jsonl",
            "nodes": node_count,
            "rels": rel_count,
            "embeddings_excluded": True,
        }

    except (ServiceUnavailable, AuthError) as e:
        return {"success": False, "error": f"Neo4j connection failed: {e}"}
    except Exception as e:
        return {"success": False, "error": str(e)}
