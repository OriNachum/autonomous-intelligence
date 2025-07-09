#!/bin/bash
set -e

echo "=========================================="
echo "Gemma3n API Server - Starting up"
echo "=========================================="
echo "Model: ${MODEL_NAME:-google/gemma-3n-e4b}"
echo "Port: ${PORT:-8000}"
echo "Device: $(nvidia-smi -L 2>/dev/null || echo 'No GPU detected')"
echo "=========================================="

# Check if model exists in cache
MODEL_CACHE_DIR="${HF_HOME:-/root/.cache/huggingface}"
echo "Model cache directory: ${MODEL_CACHE_DIR}"

# Create cache directory if it doesn't exist
mkdir -p "${MODEL_CACHE_DIR}"

# Check if we should download the model first
if [ "${DOWNLOAD_MODEL_ON_START:-true}" = "true" ]; then
    echo ""
    echo "Checking/downloading model..."
    echo "This may take several minutes on first run..."
    echo ""
    
    python3 download_model.py
    
    if [ $? -ne 0 ]; then
        echo "Failed to download model. Exiting."
        exit 1
    fi
    
    echo ""
    echo "Model ready!"
    echo ""
fi

# Start the API server
echo "Starting API server..."
echo "=========================================="

exec python3 app.py