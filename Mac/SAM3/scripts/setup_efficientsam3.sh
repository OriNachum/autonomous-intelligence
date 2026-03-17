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

# Install base package (without stage1 extras — decord has no macOS wheels)
echo "Installing EfficientSAM3 base package..."
uv pip install -e "$REPO_DIR"

# Install stage1 deps that work on macOS (skip decord, mmengine, mmcv)
echo "Installing additional dependencies for macOS..."
uv pip install \
    "opencv-python>=4.9.0.80" \
    "scipy>=1.10.0" \
    "scikit-image>=0.21.0" \
    "einops>=0.7.0" \
    "hydra-core>=1.3.2" \
    "pycocotools>=2.0.7"

echo "Done. Note: 'decord' is not available on macOS ARM64."
echo "Video-related features may not work, but image inference is fully supported."
