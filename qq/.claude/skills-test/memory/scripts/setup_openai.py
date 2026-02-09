#!/usr/bin/env python3
"""Configure an OpenAI-compatible endpoint in config.json."""

import argparse
import json
import sys
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(
        description="Configure OpenAI-compatible LLM endpoint",
        epilog="Examples:\n"
               "  setup_openai.py --base-url https://api.openai.com/v1 --api-key sk-... --model gpt-4o\n"
               "  setup_openai.py --base-url http://localhost:11434/v1 --model llama3  # Ollama\n",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--base-url", required=True, help="OpenAI-compatible API base URL")
    parser.add_argument("--api-key", default="NO_NEED", help="API key (default: NO_NEED for local)")
    parser.add_argument("--model", required=True, help="Model identifier")
    parser.add_argument("--config", default=None, help="Path to config.json")

    args = parser.parse_args()

    config_path = Path(args.config) if args.config else Path(__file__).parent.parent / "config.json"

    # Load existing config or start fresh
    if config_path.exists():
        with open(config_path) as f:
            config = json.load(f)
    else:
        config = {}

    # Update LLM section
    if "llm" not in config:
        config["llm"] = {}

    config["llm"]["base_url"] = args.base_url
    config["llm"]["api_key"] = args.api_key
    config["llm"]["model_id"] = args.model

    # Write back
    with open(config_path, "w") as f:
        json.dump(config, f, indent=2)
        f.write("\n")

    print(f"Updated {config_path}:")
    print(f"  base_url: {args.base_url}")
    print(f"  api_key:  {'***' + args.api_key[-4:] if len(args.api_key) > 8 else args.api_key}")
    print(f"  model_id: {args.model}")


if __name__ == "__main__":
    main()
