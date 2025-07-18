#!/bin/bash

# SGLang Gemma 3n API Server Entrypoint

set -e

echo "Starting Gemma 3n SGLang API Server..."

# Set default environment variables
export HOST=${HOST:-"0.0.0.0"}
export PORT=${PORT:-8080}
export SGLANG_URL=${SGLANG_URL:-"http://localhost:30000"}
export MODEL_NAME=${MODEL_NAME:-"gemma3n"}
export ENABLE_AUDIO=${ENABLE_AUDIO:-"true"}

# Log configuration
echo "Configuration:"
echo "  HOST: $HOST"
echo "  PORT: $PORT"
echo "  SGLANG_URL: $SGLANG_URL"
echo "  MODEL_NAME: $MODEL_NAME"
echo "  ENABLE_AUDIO: $ENABLE_AUDIO"

# Wait for SGLang server to be ready
echo "Waiting for SGLang server at $SGLANG_URL..."
while ! curl -s "$SGLANG_URL/health" > /dev/null 2>&1; do
    echo "  SGLang server not ready, waiting 5 seconds..."
    sleep 5
done
echo "SGLang server is ready!"

# Start the FastAPI server
echo "Starting FastAPI server..."
exec python app.py