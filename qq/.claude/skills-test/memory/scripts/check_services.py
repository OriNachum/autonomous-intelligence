#!/usr/bin/env python3
"""Health-check all memory backend services."""

import argparse
import json
import os
import sys
import urllib.request
import urllib.error
from pathlib import Path


def load_config(config_path=None):
    """Load config.json with env-var overrides."""
    defaults = {
        "llm": {"base_url": "http://localhost:8100/v1", "api_key": "NO_NEED", "model_id": ""},
        "embeddings": {"base_url": "http://localhost:8101/v1", "model": ""},
        "mongodb": {"uri": "mongodb://localhost:27017", "database": "qq_memory", "collection": "notes"},
        "neo4j": {"uri": "bolt://localhost:7687", "user": "neo4j", "password": "refinerypass"},
    }

    if config_path is None:
        config_path = Path(__file__).parent.parent / "config.json"

    if Path(config_path).exists():
        with open(config_path) as f:
            file_config = json.load(f)
        for section in defaults:
            if section in file_config:
                defaults[section].update(file_config[section])

    env_map = {
        "VLLM_URL": ("llm", "base_url"),
        "OPENAI_BASE_URL": ("llm", "base_url"),
        "TEI_URL": ("embeddings", "base_url"),
        "MONGODB_URI": ("mongodb", "uri"),
        "NEO4J_URI": ("neo4j", "uri"),
        "NEO4J_USER": ("neo4j", "user"),
        "NEO4J_PASSWORD": ("neo4j", "password"),
    }
    for env_key, (section, field) in env_map.items():
        val = os.getenv(env_key)
        if val:
            defaults[section][field] = val

    return defaults


def check_http(url, timeout=3):
    """Check if an HTTP endpoint is reachable."""
    try:
        # Try /models for OpenAI-compat, /health for TEI
        for path in ["/models", "/health", ""]:
            check_url = url.rstrip("/") + path
            req = urllib.request.Request(check_url, method="GET")
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                if resp.status == 200:
                    return True, None
    except urllib.error.URLError as e:
        return False, str(e.reason)
    except Exception as e:
        return False, str(e)
    return False, "No valid endpoint found"


def check_mongodb(uri, timeout=3):
    """Check MongoDB connectivity."""
    try:
        from pymongo import MongoClient
        client = MongoClient(uri, serverSelectionTimeoutMS=timeout * 1000)
        client.admin.command("ping")
        client.close()
        return True, None
    except ImportError:
        return False, "pymongo not installed"
    except Exception as e:
        return False, str(e)


def check_neo4j(uri, user, password, timeout=3):
    """Check Neo4j connectivity."""
    try:
        from neo4j import GraphDatabase
        driver = GraphDatabase.driver(uri, auth=(user, password))
        driver.verify_connectivity()
        driver.close()
        return True, None
    except ImportError:
        return False, "neo4j driver not installed"
    except Exception as e:
        return False, str(e)


def main():
    parser = argparse.ArgumentParser(description="Check memory service health")
    parser.add_argument("--config", default=None, help="Path to config.json")
    parser.add_argument("--json", action="store_true", help="Output as JSON")
    args = parser.parse_args()

    config = load_config(args.config)
    results = {}

    # MongoDB
    ok, err = check_mongodb(config["mongodb"]["uri"])
    results["mongodb"] = {
        "status": "connected" if ok else "unavailable",
        "url": config["mongodb"]["uri"],
    }
    if err:
        results["mongodb"]["error"] = err

    # Neo4j
    ok, err = check_neo4j(config["neo4j"]["uri"], config["neo4j"]["user"], config["neo4j"]["password"])
    results["neo4j"] = {
        "status": "connected" if ok else "unavailable",
        "url": config["neo4j"]["uri"],
    }
    if err:
        results["neo4j"]["error"] = err

    # TEI / Embeddings
    ok, err = check_http(config["embeddings"]["base_url"])
    results["tei"] = {
        "status": "connected" if ok else "unavailable",
        "url": config["embeddings"]["base_url"],
    }
    if err:
        results["tei"]["error"] = err

    # LLM
    ok, err = check_http(config["llm"]["base_url"])
    results["llm"] = {
        "status": "connected" if ok else "unavailable",
        "url": config["llm"]["base_url"],
    }
    if err:
        results["llm"]["error"] = err

    if args.json:
        print(json.dumps(results, indent=2))
    else:
        for service, info in results.items():
            mark = "\u2713" if info["status"] == "connected" else "\u2717"
            line = f"  {service:12s} {mark} {info['status']:12s} ({info['url']})"
            if "error" in info:
                line += f"  [{info['error']}]"
            print(line)

    all_ok = all(r["status"] == "connected" for r in results.values())
    sys.exit(0 if all_ok else 1)


if __name__ == "__main__":
    main()
