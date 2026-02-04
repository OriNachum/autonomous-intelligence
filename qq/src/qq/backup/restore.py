"""Restore functions for memory stores.

Reads JSONL format with streaming and optionally regenerates embeddings.
"""

import json
import os
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, Optional


def restore_notes(backup_path: Path) -> Dict[str, Any]:
    """
    Restore notes.md from backup.

    Args:
        backup_path: Path to backup directory

    Returns:
        {"success": True, "restored": True} or {"success": False, "error": str}
    """
    from qq.memory.notes import NotesManager

    notes_file = backup_path / "notes.md"
    if not notes_file.exists():
        return {"success": False, "error": "notes.md not found in backup"}

    try:
        content = notes_file.read_text()
        manager = NotesManager()

        # Write directly to the notes file
        manager._content = content
        manager._save()

        return {"success": True, "restored": True, "size_bytes": len(content)}
    except Exception as e:
        return {"success": False, "error": str(e)}


def restore_mongodb(
    backup_path: Path,
    embeddings: Optional[Any] = None,
    skip_embeddings: bool = False,
) -> Dict[str, Any]:
    """
    Restore MongoDB from JSONL backup with streaming read.

    - Reads line by line (constant memory)
    - Optionally regenerates embeddings for each note
    - Uses upsert to avoid duplicates

    Args:
        backup_path: Path to backup directory
        embeddings: EmbeddingClient instance for regenerating embeddings
        skip_embeddings: If True, skip embedding regeneration (faster)

    Returns:
        {"success": True, "restored": count, "embedding_errors": count}
    """
    from pymongo import MongoClient
    from pymongo.errors import ConnectionFailure, ServerSelectionTimeoutError

    jsonl_file = backup_path / "mongodb_notes.jsonl"
    if not jsonl_file.exists():
        return {"success": False, "error": "mongodb_notes.jsonl not found in backup"}

    uri = os.getenv("MONGODB_URI", "mongodb://localhost:27017")

    try:
        client = MongoClient(uri, serverSelectionTimeoutMS=5000)
        client.admin.command("ping")
        collection = client["qq_memory"]["notes"]

        count = 0
        embedding_errors = 0

        with open(jsonl_file, "r") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue

                record = json.loads(line)

                # Regenerate embedding from content if requested
                embedding = []
                if not skip_embeddings and embeddings and record.get("content"):
                    try:
                        embedding = embeddings.get_embedding(record["content"])
                    except Exception:
                        embedding_errors += 1

                # Parse updated_at
                updated_at = datetime.utcnow()
                if record.get("updated_at"):
                    try:
                        updated_at = datetime.fromisoformat(record["updated_at"])
                    except Exception:
                        pass

                # Upsert to collection
                collection.update_one(
                    {"note_id": record["note_id"]},
                    {
                        "$set": {
                            "note_id": record["note_id"],
                            "content": record.get("content"),
                            "section": record.get("section"),
                            "metadata": record.get("metadata", {}),
                            "embedding": embedding,
                            "updated_at": updated_at,
                        }
                    },
                    upsert=True,
                )
                count += 1

        client.close()

        return {
            "success": True,
            "restored": count,
            "embedding_errors": embedding_errors,
            "embeddings_regenerated": not skip_embeddings and embeddings is not None,
        }

    except (ConnectionFailure, ServerSelectionTimeoutError) as e:
        return {"success": False, "error": f"MongoDB connection failed: {e}"}
    except Exception as e:
        return {"success": False, "error": str(e)}


def restore_neo4j(
    backup_path: Path,
    embeddings: Optional[Any] = None,
    skip_embeddings: bool = False,
) -> Dict[str, Any]:
    """
    Restore Neo4j from JSONL backup with streaming read.

    - Pass 1: Create all nodes with embeddings
    - Pass 2: Create all relationships

    Args:
        backup_path: Path to backup directory
        embeddings: EmbeddingClient instance for regenerating embeddings
        skip_embeddings: If True, skip embedding regeneration (faster)

    Returns:
        {"success": True, "nodes": count, "relationships": count, "embedding_errors": count}
    """
    from neo4j import GraphDatabase
    from neo4j.exceptions import ServiceUnavailable, AuthError

    jsonl_file = backup_path / "neo4j_graph.jsonl"
    if not jsonl_file.exists():
        return {"success": False, "error": "neo4j_graph.jsonl not found in backup"}

    uri = os.getenv("NEO4J_URI", "bolt://localhost:7687")
    user = os.getenv("NEO4J_USER", "neo4j")
    password = os.getenv("NEO4J_PASSWORD", "refinerypass")

    try:
        driver = GraphDatabase.driver(uri, auth=(user, password))
        driver.verify_connectivity()

        nodes = 0
        rels = 0
        embedding_errors = 0

        with driver.session() as session:
            # Pass 1: Create nodes
            with open(jsonl_file, "r") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue

                    record = json.loads(line)
                    if record.get("_type") != "node":
                        continue

                    # Skip nodes without name
                    if not record.get("name"):
                        continue

                    # Regenerate embedding
                    embedding = None
                    if not skip_embeddings and embeddings and record.get("name"):
                        try:
                            embed_text = (
                                f"{record['name']}: {record.get('description', '')}"
                            )
                            embedding = embeddings.get_embedding(embed_text)
                        except Exception:
                            embedding_errors += 1

                    labels = record.get("labels", ["Entity"])
                    if not labels:
                        labels = ["Entity"]
                    labels_str = ":".join(labels)

                    props = {
                        "name": record["name"],
                        "description": record.get("description"),
                        **record.get("properties", {}),
                    }
                    if embedding:
                        props["embedding"] = embedding

                    # Remove None values
                    props = {k: v for k, v in props.items() if v is not None}

                    session.run(
                        f"MERGE (n:{labels_str} {{name: $name}}) SET n = $props",
                        {"name": record["name"], "props": props},
                    )
                    nodes += 1

            # Pass 2: Create relationships
            with open(jsonl_file, "r") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue

                    record = json.loads(line)
                    if record.get("_type") != "relationship":
                        continue

                    source = record.get("source")
                    target = record.get("target")
                    rel_type = record.get("rel_type", "RELATES_TO")

                    if not source or not target:
                        continue

                    # Sanitize relationship type (no spaces, uppercase)
                    rel_type = rel_type.upper().replace(" ", "_")

                    props = record.get("properties", {})

                    session.run(
                        f"""
                        MATCH (a {{name: $source}}), (b {{name: $target}})
                        MERGE (a)-[r:{rel_type}]->(b)
                        SET r = $props
                        """,
                        {"source": source, "target": target, "props": props},
                    )
                    rels += 1

        driver.close()

        return {
            "success": True,
            "nodes": nodes,
            "relationships": rels,
            "embedding_errors": embedding_errors,
            "embeddings_regenerated": not skip_embeddings and embeddings is not None,
        }

    except (ServiceUnavailable, AuthError) as e:
        return {"success": False, "error": f"Neo4j connection failed: {e}"}
    except Exception as e:
        return {"success": False, "error": str(e)}


def restore_all(
    backup_path: Path,
    embeddings: Optional[Any] = None,
    skip_embeddings: bool = False,
    notes_only: bool = False,
) -> Dict[str, Any]:
    """
    Restore all stores from a backup.

    Args:
        backup_path: Path to backup directory
        embeddings: EmbeddingClient for regenerating embeddings
        skip_embeddings: Skip embedding regeneration (faster)
        notes_only: Only restore notes.md file

    Returns:
        Dict with results for each store
    """
    results = {}

    # Always restore notes
    results["notes"] = restore_notes(backup_path)

    if not notes_only:
        results["mongodb"] = restore_mongodb(backup_path, embeddings, skip_embeddings)
        results["neo4j"] = restore_neo4j(backup_path, embeddings, skip_embeddings)

    # Overall success
    results["success"] = all(r.get("success", False) for r in results.values())

    return results
