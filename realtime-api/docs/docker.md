# Docker Architecture

The Realtime API runs as a three-service Docker Compose stack. Two GPU-accelerated ML services (TTS and STT) sit behind a lightweight CPU-only Python bridge that exposes the OpenAI Realtime WebSocket protocol.

## Services

### magpie-tts (Qwen3 TTS)

Text-to-speech powered by Qwen3-TTS via vLLM-Omni.

| Setting | Default | Description |
|---------|---------|-------------|
| Port | `8091` | HTTP API for speech synthesis |
| Model | `Qwen/Qwen3-TTS-12Hz-1.7B-CustomVoice` | HuggingFace model ID |
| Health check | `GET /health` | Polled every 30s, 300s startup grace |
| GPU | All available | NVIDIA runtime with IPC host |

Builds from `../qwen3-tts/Dockerfile`, which uses `scitrera/dgx-spark-vllm:0.16.0-t4` as base. This image has vLLM pre-compiled for DGX Spark (aarch64). The build clones `vllm-omni`, installs audio processing dependencies (ffmpeg, sox, omegaconf, resampy, librosa, etc.), and copies the custom stage config.

The stage config (`stage_configs/qwen3_tts.yaml`) defines a two-stage vLLM pipeline:
- **Stage 0 (Talker)**: Autoregressive text-to-speech-code model, 15% GPU memory
- **Stage 1 (Code2Wav)**: Speech codes to audio waveform, 15% GPU memory

Both stages share GPU 0 with batch size 1 and communicate via shared memory connector with codec streaming enabled (25-frame chunks).

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
QWEN3_TTS_PORT=8091
PARAKEET_PORT=9002
REALTIME_API_PORT=8080

# TTS model
QWEN3_TTS_MODEL=Qwen/Qwen3-TTS-12Hz-1.7B-CustomVoice

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
2. `magpie-tts` loads the Qwen3 TTS model (up to 5 minutes, startup grace: 300s)
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
