#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
REPO_DIR="$PROJECT_DIR/efficientsam3"

if [ -d "$REPO_DIR" ]; then
    echo "EfficientSAM3 already cloned at $REPO_DIR"
    cd "$REPO_DIR" && git pull
else
    echo "Cloning EfficientSAM3..."
    git clone https://github.com/SimonZeng7108/EfficientSAM3.git "$REPO_DIR"
fi

cd "$PROJECT_DIR"
echo "Installing EfficientSAM3 into project venv..."
uv pip install -e "$REPO_DIR[stage1]"
echo "Done."
