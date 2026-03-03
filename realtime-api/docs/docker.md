# Docker Architecture

The Realtime API runs as a three-service Docker Compose stack. Two GPU-accelerated ML services (TTS and STT) sit behind a lightweight CPU-only Python bridge that exposes the OpenAI Realtime WebSocket protocol.

## Services

### magpie-tts (Magpie TTS NIM)

Text-to-speech powered by NVIDIA Magpie TTS NIM — a multilingual TTS service with multiple voices and emotions.

| Setting | Default | Description |
|---------|---------|-------------|
| Port | `8091` | HTTP API for speech synthesis |
| Image | `nvcr.io/nim/nvidia/magpie-tts-multilingual:latest` | NVIDIA NIM container |
| Health check | `GET /health` | Polled every 30s, 300s startup grace |
| GPU | All available | NVIDIA runtime with IPC host |

Runs as a pre-built NIM container pulled from NVIDIA NGC. No local build step required — the container includes the model and serving infrastructure.

### parakeet-stt (Parakeet ASR)

Speech-to-text powered by NVIDIA Parakeet TDT 0.6B.

| Setting | Default | Description |
|---------|---------|-------------|
| Port | `9002` | HTTP API for transcription |
| Model | `nvidia/parakeet-tdt-0.6b-v2` | NeMo ASR model |
| Health check | `GET /v1/health/ready` | Polled every 30s, 120s startup grace |
| GPU | All available | NVIDIA runtime with IPC host |

Builds from `../qwen3-tts/Dockerfile.parakeet`. Same base image, installs `nemo_toolkit[asr]`, and pre-downloads the Parakeet model during build. Runs a FastAPI server (`listen_server.py`) that accepts WAV uploads at 16kHz and returns transcription JSON.

### realtime-api (Bridge)

The WebSocket bridge that ties everything together.

| Setting | Default | Description |
|---------|---------|-------------|
| Port | `8080` | WebSocket + HTTP API |
| GPU | None | CPU-only (VAD runs on CPU via torch) |
| Health check | `GET /health` | Basic readiness probe |
| Dependencies | magpie-tts, parakeet-stt | Waits for both services to be healthy |

Builds from the local `Dockerfile` — `python:3.12-slim` with torch, silero-vad, fastapi, httpx, scipy, numpy. The image is ~2GB due to torch but requires no GPU at runtime.

## Shared Resources

### HuggingFace Cache Volume

```yaml
volumes:
  hf-cache:
```

Both `magpie-tts` and `parakeet-stt` mount this volume at `/root/.cache/huggingface`. Models are downloaded once and shared, saving ~10GB+ of disk and avoiding redundant downloads.

### Docker Network

All services communicate via Docker's internal DNS:
- `realtime-api` calls `http://magpie-tts:8091` for TTS
- `realtime-api` calls `http://parakeet-stt:9002` for STT
- The LLM backend runs on the host, accessed via `http://host.docker.internal:8000`

### GPU Allocation

Both ML services reserve all available GPUs:

```yaml
deploy:
  resources:
    reservations:
      devices:
        - driver: nvidia
          count: all
          capabilities: [gpu]
```

On DGX Spark with 128GB unified memory, the two TTS pipeline stages use 15% each (about 19GB per stage) and Parakeet uses additional GPU memory. The `NVIDIA_DISABLE_REQUIRE=1` environment variable suppresses strict driver version checks.

The `ipc: host` setting is required for vLLM's shared memory inter-process communication between pipeline stages.

## Environment Variables

Override via `.env` file or inline environment:

```bash
# Service ports
MAGPIE_TTS_PORT=8091
PARAKEET_PORT=9002
REALTIME_API_PORT=8080

# LLM backend (runs on host)
OPENAI_BASE_URL=http://host.docker.internal:8000
OPENAI_API_KEY=EMPTY
OPENAI_MODEL=default

# Voice and VAD
DEFAULT_VOICE=Mia.Calm
TTS_SPEED=125
DEFAULT_TURN_DETECTION=server_vad
DEFAULT_AEC_MODE=none
VAD_THRESHOLD=0.5
VAD_SILENCE_MS=600
VAD_PREFIX_PADDING_MS=300
```

## Startup Sequence

1. `docker compose up` starts all three services
2. `magpie-tts` loads the Magpie TTS NIM (up to 5 minutes, startup grace: 300s)
3. `parakeet-stt` loads Parakeet TDT (up to 2 minutes, startup grace: 120s)
4. Once both pass health checks, `realtime-api` starts
5. The bridge connects to both services via internal DNS and begins accepting WebSocket connections on port 8080

## Building

```bash
# Build all three images
docker compose build

# Start TTS and STT first (useful for debugging)
docker compose up magpie-tts parakeet-stt

# Start everything
docker compose up

# Rebuild only the bridge (fast — no model downloads)
docker compose build realtime-api
```

## Resource Considerations

On DGX Spark (128GB unified memory):
- The `data-refinery-vllm` container may occupy ~97GB GPU memory — stop it before running TTS
- Both TTS pipeline stages are configured for 15% GPU memory each (reduced from defaults)
- Parakeet is lightweight (~0.6B params) and uses minimal GPU memory
- The bridge container needs ~2GB RAM for torch + VAD, no GPU

All services have `restart: unless-stopped` for automatic recovery after crashes or reboots.
