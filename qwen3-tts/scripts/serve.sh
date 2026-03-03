#!/usr/bin/env bash
# Start Qwen3-TTS via Docker Compose.
#
# Usage:
#   bash scripts/serve.sh                  # CustomVoice model (voice design + emotion)
#   bash scripts/serve.sh base             # Base model (voice cloning)
#   bash scripts/serve.sh /path/to/model   # Fine-tuned checkpoint

set -euo pipefail

cd "$(dirname "$0")/.."

MODEL_ARG="${1:-}"

if [ -z "$MODEL_ARG" ]; then
    MODEL="Qwen/Qwen3-TTS-12Hz-1.7B-CustomVoice"
elif [ "$MODEL_ARG" = "base" ]; then
    MODEL="Qwen/Qwen3-TTS-12Hz-1.7B-Base"
else
    MODEL="$MODEL_ARG"
fi

PORT="${QWEN3_TTS_PORT:-8091}"

echo "==> Starting Qwen3-TTS (Docker)"
echo "    Model: $MODEL"
echo "    Port:  $PORT"

QWEN3_TTS_MODEL="$MODEL" QWEN3_TTS_PORT="$PORT" docker compose up -d

echo "==> Container started. Waiting for health check..."
echo "    curl http://localhost:$PORT/health"
echo "    docker compose logs -f"
