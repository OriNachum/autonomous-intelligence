#!/usr/bin/env python3
"""Start/stop memory backend services via docker-compose."""

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

VALID_SERVICES = {"mongodb", "neo4j", "tei"}


def load_compose_path(config_path=None):
    """Get docker-compose file path from config."""
    default_compose = str(Path(__file__).parent.parent / "assets" / "docker-compose.yml")

    if config_path is None:
        config_path = Path(__file__).parent.parent / "config.json"

    if Path(config_path).exists():
        with open(config_path) as f:
            config = json.load(f)
        return config.get("docker_compose_path", default_compose)

    return default_compose


def run_compose(compose_path, action, services=None):
    """Run docker compose command."""
    if not Path(compose_path).exists():
        print(f"Error: compose file not found: {compose_path}", file=sys.stderr)
        sys.exit(1)

    cmd = ["docker", "compose", "-f", compose_path, action]

    if action == "up":
        cmd.append("-d")

    if services:
        invalid = set(services) - VALID_SERVICES
        if invalid:
            print(f"Error: unknown services: {', '.join(invalid)}", file=sys.stderr)
            print(f"Valid services: {', '.join(sorted(VALID_SERVICES))}", file=sys.stderr)
            sys.exit(1)
        cmd.extend(services)

    print(f"Running: {' '.join(cmd)}")
    result = subprocess.run(cmd, capture_output=False)
    return result.returncode


def main():
    parser = argparse.ArgumentParser(
        description="Start/stop memory backend services",
        epilog="Examples:\n"
               "  start_services.py              # start all\n"
               "  start_services.py mongodb neo4j # start subset\n"
               "  start_services.py --stop        # stop all\n"
               "  start_services.py --stop tei    # stop subset\n",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("services", nargs="*", help=f"Services to manage: {', '.join(sorted(VALID_SERVICES))}")
    parser.add_argument("--stop", action="store_true", help="Stop services instead of starting")
    parser.add_argument("--config", default=None, help="Path to config.json")

    args = parser.parse_args()

    compose_path = load_compose_path(args.config)
    action = "down" if args.stop else "up"
    services = args.services if args.services else None

    rc = run_compose(compose_path, action, services)
    sys.exit(rc)


if __name__ == "__main__":
    main()
