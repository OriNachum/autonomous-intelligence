#!/bin/bash
# Data Refinery Environment Setup using uv
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

echo "=== Data Refinery Setup ==="

# Check for uv
if ! command -v uv &> /dev/null; then
    echo "Installing uv..."
    curl -LsSf https://astral.sh/uv/install.sh | sh
fi

# Sync dependencies
echo "Syncing dependencies with uv..."
uv sync

# Create output directory
mkdir -p output

echo ""
echo "=== Setup Complete ==="
echo ""
echo "To run commands in the environment:"
echo "  uv run python refinery.py --help"
echo ""
echo "To start Neo4j:"
echo "  docker compose up -d"
echo ""
echo "To start vLLM with Nemotron (prefix caching enabled):"
echo "  vllm serve nvidia/NVIDIA-Nemotron-3-Nano-30B-A3B-FP8 \\"
echo "      --enable-prefix-caching \\"
echo "      --port 8000"
echo ""
echo "To run the refinery:"
echo "  uv run python refinery.py --input <document> --output output/"
