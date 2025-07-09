#!/bin/bash
set -e

echo "=========================================="
echo "Gemma3n API Server - Starting up"
echo "=========================================="
echo "Model: ${MODEL_NAME:-google/gemma-3n-e4b}"
echo "Port: ${PORT:-8000}"
echo "Device: $(nvidia-smi -L 2>/dev/null || echo 'No GPU detected')"
echo "=========================================="

# Model cache setup
MODEL_CACHE_DIR="${HF_HOME:-/cache/huggingface}"
echo "Model cache directory: ${MODEL_CACHE_DIR}"

# Create cache directories if they don't exist
mkdir -p "${MODEL_CACHE_DIR}" /models /app/logs

# Function to check if model exists
check_model_exists() {
    local model_name="${MODEL_NAME:-google/gemma-3n-e4b}"
    local model_hash=$(echo -n "$model_name" | sha256sum | cut -d' ' -f1)
    
    # Check for common model file patterns in cache
    if find "${MODEL_CACHE_DIR}" -name "*.bin" -o -name "*.safetensors" -o -name "pytorch_model.bin" | grep -q .; then
        echo "Found model files in cache"
        
        # Quick verification - try to load just the config
        python3 -c "
from transformers import AutoConfig
try:
    config = AutoConfig.from_pretrained('${model_name}', cache_dir='${MODEL_CACHE_DIR}')
    print('Model config verified successfully')
    exit(0)
except Exception as e:
    print(f'Model verification failed: {e}')
    exit(1)
" 2>/dev/null
        
        return $?
    else
        echo "No model files found in cache"
        return 1
    fi
}

# Check if model already exists
echo ""
echo "Checking for cached model..."

if check_model_exists; then
    echo "✓ Model found in cache, skipping download"
    echo ""
else
    echo "Model not found in cache, downloading..."
    echo "This may take 10-30 minutes on first run..."
    echo ""
    
    python3 download_model.py
    
    if [ $? -ne 0 ]; then
        echo "Failed to download model. Exiting."
        exit 1
    fi
    
    echo ""
    echo "✓ Model downloaded and cached successfully!"
    echo ""
fi

# Display cache usage
echo "Cache statistics:"
du -sh "${MODEL_CACHE_DIR}" 2>/dev/null || echo "Unable to calculate cache size"
echo ""

# Start the API server
echo "Starting API server..."
echo "=========================================="

exec python3 app.py