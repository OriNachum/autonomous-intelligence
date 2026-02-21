# Qwen3-TTS

Text-to-speech system using NVIDIA MagpieTTS, running as a Docker service with a lightweight CLI client.

## Quick Start

```bash
# Start the TTS service (first run downloads model ~1GB)
docker compose up -d

# Speak a message
uv run src/speak.py --message "Hello world"

# Different speaker and language
uv run src/speak.py --message "Hola mundo" --language es --speaker Sofia
```

## Architecture

- `src/server.py` — FastAPI server that loads MagpieTTS model at startup and serves `/health` and `/synthesize` endpoints
- `src/speak.py` — CLI client that sends HTTP requests to the service and plays returned WAV audio via `aplay`
- `Dockerfile` — Builds the server image (NVIDIA PyTorch base + NeMo TTS + FastAPI)
- `docker-compose.yaml` — Runs the service with GPU access, HF cache volume, healthcheck on port 8100

## Service

The MagpieTTS model runs inside a Docker container with GPU access. The CLI client (`speak.py`) sends HTTP requests to it.

```bash
# Start service
docker compose up -d

# Check health
curl http://localhost:8100/health

# Synthesize directly
curl -X POST http://localhost:8100/synthesize \
  -H 'Content-Type: application/json' \
  -d '{"message":"Hello"}' -o test.wav

# Stop service
docker compose down
```

Default service URL: `http://localhost:8100` (override with `--server-url` or `MAGPIETTS_URL` env var).

## Dependencies

Managed by `uv`. Client deps: `httpx`, `soundfile`. Server deps (in Docker): `nemo_toolkit[tts]`, `kaldialign`, `fastapi`, `uvicorn`.

## Model

Uses `nvidia/magpie_tts_multilingual_357m` via NeMo. Audio at 22kHz via NanoCodec. Speakers: John, Sofia, Aria, Jason, Leo. Languages: en, es, de, fr, vi, it, zh.
