# Docker Compose — Docker-First Approach

All services run as containers orchestrated by Docker Compose. No local Python environment needed.

---

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                        DGX Spark (128 GB GPU)                   │
│                                                                 │
│  ┌──────────────┐  ┌──────────────┐  ┌────────────────────────┐│
│  │  magpie-tts  │  │ parakeet-stt │  │       vllm-llm         ││
│  │  :9000       │  │  :9002       │  │       :8000             ││
│  │  NIM image   │  │  Custom build│  │  NVIDIA vLLM image     ││
│  │  ~10 GB GPU  │  │  ~2 GB GPU   │  │  ~77 GB GPU (0.60)     ││
│  └──────┬───────┘  └──────┬───────┘  └───────────┬────────────┘│
│         │                 │                       │             │
│  ┌──────┴─────────────────┴───────────────────────┴────────────┐│
│  │                    realtime-api  :8080                       ││
│  │              FastAPI WebSocket Bridge                        ││
│  │         Audio In → VAD → STT → LLM → TTS → Audio Out       ││
│  └─────────────────────────────────────────────────────────────┘│
│                                                                 │
│  Volumes:  hf-cache (shared HF models)  │  nim-cache (NIM)     │
└─────────────────────────────────────────────────────────────────┘
```

---

## Quick Start

```bash
# 1. Copy and edit environment file
cp .env.example .env

# 2. Set required tokens
#    - HF_TOKEN: HuggingFace token (for gated model downloads)
#    - NGC_API_KEY: NVIDIA NGC key (for Magpie TTS NIM)
nano .env

# 3. Start all services
docker compose up -d

# 4. Wait for health checks (vLLM and Magpie have long startup)
docker compose ps     # check status
docker compose logs -f vllm-llm   # watch vLLM download & load model

# 5. Verify all services are healthy
curl http://localhost:8000/health          # vLLM
curl http://localhost:9000/v1/health/ready # Magpie TTS
curl http://localhost:9002/v1/health/ready # Parakeet STT
curl http://localhost:8080/health          # Bridge
```

---

## Service Summary

| Service | Image / Build | Port | GPU | Health Endpoint | Start Period |
|---------|---------------|------|-----|-----------------|-------------|
| `vllm-llm` | `nvcr.io/nvidia/vllm:25.12.post1-py3` | 8000 | ~77 GB (60%) | `GET /health` | 600s |
| `magpie-tts` | `nvcr.io/nim/nvidia/magpie-tts-multilingual:latest` | 9000 | NIM-managed | `GET /v1/health/ready` | 300s |
| `parakeet-stt` | Build: `../qwen3-tts/Dockerfile.parakeet` | 9002 | ~2 GB | `GET /v1/health/ready` | 600s |
| `realtime-api` | Build: `./Dockerfile` | 8080 | None (CPU) | `GET /health` | — |

---

## Startup Order & Dependencies

The `realtime-api` bridge waits for all three backend services to become healthy before starting:

```yaml
realtime-api:
  depends_on:
    magpie-tts:
      condition: service_healthy
    parakeet-stt:
      condition: service_healthy
    vllm-llm:
      condition: service_healthy
```

**Typical startup timeline:**

```
t=0m     All containers start
t=1-2m   parakeet-stt becomes healthy (model download on first run: longer)
t=3-5m   magpie-tts becomes healthy (NIM initialization)
t=5-10m  vllm-llm becomes healthy (model download + KV cache allocation)
t=~10m   realtime-api starts (all dependencies healthy)
```

First run takes longer due to model downloads. Subsequent starts use cached models from volumes.

---

## Complete `.env` Reference

```bash
# ─── vLLM LLM Service ──────────────────────────────────────────
VLLM_MODEL=nvidia/NVIDIA-Nemotron-3-Nano-30B-A3B-FP8  # HF model ID
VLLM_PORT=8000                    # HTTP port
VLLM_GPU_MEMORY=0.75              # Fraction of GPU for KV cache (0.0–1.0)
VLLM_MAX_NUM_SEQS=8               # Max concurrent sequences
VLLM_MAX_MODEL_LEN=131072         # Max context length (tokens)
VLLM_TOOL_CALL_PARSER=qwen3_coder # Tool call parser
HF_TOKEN=                         # ⚠️ REQUIRED — HuggingFace token

# ─── LLM Client (Bridge → vLLM) ────────────────────────────────
OPENAI_BASE_URL=http://vllm-llm:8000  # Internal Docker network URL
OPENAI_API_KEY=EMPTY                   # vLLM doesn't enforce auth
OPENAI_MODEL=nvidia/NVIDIA-Nemotron-3-Nano-30B-A3B-FP8

# ─── Magpie TTS NIM ────────────────────────────────────────────
NGC_API_KEY=                      # ⚠️ REQUIRED — NVIDIA NGC API key
MAGPIE_TTS_PORT=9000              # HTTP port

# ─── Parakeet STT ──────────────────────────────────────────────
PARAKEET_PORT=9002                # HTTP port

# ─── Bridge Defaults ───────────────────────────────────────────
DEFAULT_VOICE=Mia.Calm            # Default TTS voice
TTS_SPEED=125                     # Speech speed percentage (100=normal)
DEFAULT_TURN_DETECTION=server_vad # server_vad or disable
DEFAULT_AEC_MODE=none             # none or aec (barge-in)
VAD_THRESHOLD=0.5                 # Speech detection sensitivity (0.0–1.0)
VAD_SILENCE_MS=600                # Silence to end turn (ms)
VAD_PREFIX_PADDING_MS=300         # Audio kept before speech start (ms)
```

---

## Volumes

| Volume | Mount Point | Used By | Purpose |
|--------|------------|---------|---------|
| `hf-cache` | `/root/.cache/huggingface` | `vllm-llm`, `parakeet-stt` | Shared HuggingFace model cache — prevents duplicate downloads |
| `nim-cache` | `/opt/nim/.cache` | `magpie-tts` | NVIDIA NIM model cache |

Volumes persist across container restarts. To force a fresh model download:

```bash
docker volume rm realtime-api_hf-cache
docker volume rm realtime-api_nim-cache
```

---

## GPU Allocation on DGX Spark (128 GB)

All services share the single GPU via `NVIDIA_VISIBLE_DEVICES=all`:

| Service | Memory Usage | Notes |
|---------|-------------|-------|
| `vllm-llm` | ~77 GB (`gpu-memory-utilization: 0.60`) | Largest consumer. Model weights + KV cache |
| `parakeet-stt` | ~2 GB | Small ASR model (0.6B params) |
| `magpie-tts` | ~10 GB | NIM-managed allocation |
| **Total** | **~89 GB** | Leaves ~39 GB headroom |

To adjust vLLM's share, change `VLLM_GPU_MEMORY` in `.env`:
- `0.60` — default, ~77 GB (conservative, room for other services)
- `0.75` — ~96 GB (larger KV cache, longer contexts)
- `0.50` — ~64 GB (if running other GPU workloads alongside)

---

## Common Operations

### Start a specific service

```bash
docker compose up -d vllm-llm
```

### Rebuild the bridge after code changes

```bash
docker compose build realtime-api && docker compose up -d realtime-api
```

### View logs

```bash
# All services
docker compose logs -f

# Single service
docker compose logs -f vllm-llm

# Last 50 lines
docker compose logs --tail 50 realtime-api
```

### Stop everything

```bash
docker compose down
```

### Reset model cache (force re-download)

```bash
docker compose down
docker volume rm realtime-api_hf-cache realtime-api_nim-cache
docker compose up -d
```

### Check GPU usage

```bash
nvidia-smi
```

### Shell into a container

```bash
docker compose exec vllm-llm bash
docker compose exec realtime-api bash
```

---

## Health Check Details

| Service | Method | Endpoint | Interval | Timeout | Retries | Start Period |
|---------|--------|----------|----------|---------|---------|-------------|
| `vllm-llm` | curl | `http://localhost:8000/health` | 30s | 10s | 5 | 600s |
| `magpie-tts` | curl | `http://localhost:9000/v1/health/ready` | 30s | 10s | 5 | 300s |
| `parakeet-stt` | python urllib | `http://localhost:9002/v1/health/ready` | 30s | 10s | 3 | 600s |
| `realtime-api` | — | — | — | — | — | — |

The bridge (`realtime-api`) doesn't define its own health check in Docker — it has a `GET /health` endpoint that returns `{"status": "ok"}` but relies on `depends_on` conditions for startup ordering.

---

## Troubleshooting

### vLLM won't start / OOM

```
torch.cuda.OutOfMemoryError: CUDA out of memory
```

- Lower `VLLM_GPU_MEMORY` in `.env` (e.g., `0.50`)
- Stop other GPU-consuming containers: `docker ps` → `docker stop <container>`
- Check GPU usage: `nvidia-smi`

### Magpie TTS returns errors

```
TTS error 500
```

- Verify `NGC_API_KEY` is set and valid in `.env`
- Check NIM initialization: `docker compose logs magpie-tts`
- Ensure the NIM cache volume has write permissions

### Parakeet returns empty transcriptions

- Check audio format: 16 kHz, PCM16 mono WAV works best
- Check if model downloaded: `docker compose logs parakeet-stt`
- Test directly: `curl -X POST http://localhost:9002/v1/audio/transcriptions -F "file=@test.wav"`

### Bridge can't connect to services

```
Cannot connect to LLM at http://vllm-llm:8000
```

- Ensure all services are healthy: `docker compose ps`
- Check Docker network: `docker network ls`
- Verify internal URLs match service names in `docker-compose.yaml`

### Model download stuck / slow

- Check network: `docker compose exec vllm-llm curl -I https://huggingface.co`
- Verify `HF_TOKEN` is valid (for gated models)
- Models are cached in Docker volumes — first download is slow, subsequent starts are fast

### WebSocket connection refused

- Ensure bridge is running: `docker compose ps realtime-api`
- Check bridge logs: `docker compose logs realtime-api`
- Verify port mapping: `docker compose port realtime-api 8080`
- Test health: `curl http://localhost:8080/health`

### Audio playback issues

- The bridge expects PCM16 at 24 kHz from the client
- TTS outputs 22050 Hz, bridge resamples to 24 kHz automatically
- Check for resampling errors in bridge logs
