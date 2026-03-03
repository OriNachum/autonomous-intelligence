# Qwen3-TTS

Text-to-speech system using Qwen3-TTS (1.7B) served via Docker with vLLM-Omni on DGX Spark.

## Quick Start

```bash
# Build and start the server
docker compose up -d

# Or use the helper script
bash scripts/serve.sh

# Speak a message
uv run src/speak.py --message "Hello world"

# With emotion/style
uv run src/speak.py --message "Great news!" --instructions "excited"

# Different voice
uv run src/speak.py --message "Hi there" --voice ryan

# Stop the server
docker compose down
```

## Architecture

- `src/speak.py` — CLI client that sends HTTP requests to vLLM-Omni and plays returned WAV audio via `aplay`
- `Dockerfile` — Builds vLLM-Omni image on `scitrera/dgx-spark-vllm:0.16.0-t4` (DGX Spark compatible)
- `stage_configs/qwen3_tts.yaml` — vLLM-Omni stage config tuned for DGX Spark unified memory
- `docker-compose.yaml` — Runs the server container with GPU access and model caching
- `scripts/serve.sh` — Convenience wrapper: selects model and runs `docker compose up -d`
- `scripts/prepare_data.sh` — Encodes audio into discrete codes for fine-tuning
- `scripts/train.sh` — Fine-tunes Qwen3-TTS on prepared data
- `scripts/record_voice.py` — Records voice samples for training/cloning

## Prerequisites

- Docker with NVIDIA Container Toolkit (`nvidia-ctk`)
- `aplay` (ALSA/PipeWire for audio playback on host)

## Server

The Docker image is based on `scitrera/dgx-spark-vllm:0.16.0-t4` (vLLM compiled for DGX Spark) with vllm-omni layered on top.

```bash
# Build image
docker compose build

# Start server (CustomVoice model — voice design + emotion)
bash scripts/serve.sh

# Start with Base model (voice cloning)
bash scripts/serve.sh base

# Start with fine-tuned checkpoint
bash scripts/serve.sh /path/to/checkpoint

# View logs
docker compose logs -f

# Check health
curl http://localhost:8091/health

# Synthesize directly
curl -X POST http://localhost:8091/v1/audio/speech \
  -H 'Content-Type: application/json' \
  -H 'Authorization: Bearer EMPTY' \
  -d '{"model":"Qwen/Qwen3-TTS-12Hz-1.7B-CustomVoice","input":"Hello","voice":"vivian"}' \
  -o test.wav

# Stop server
docker compose down
```

Default port: 8091 (override with `QWEN3_TTS_PORT` env var for both server and client).

Model selection: set `QWEN3_TTS_MODEL` env var or pass argument to `scripts/serve.sh`.

## CLI Options

- `--message` / `-m` — Text to synthesize (required)
- `--voice` / `-v` — Voice: vivian, ryan, aiden, dylan, eric, ono_anna, serena, sohee, uncle_fu (default: vivian)
- `--instructions` / `-i` — Emotion/style instructions (e.g. "excited", "whisper", "sad")
- `--task-type` / `-t` — Task type: CustomVoice, Base, VoiceDesign (default: CustomVoice)
- `--ref-audio` — Path to reference WAV for voice cloning (Base task)
- `--ref-text` — Transcript of the reference audio
- `--server-url` — vLLM-Omni server URL (env: `QWEN3_TTS_URL`, default: `http://localhost:8091`)

## Task Types

| Type | Model | Use Case |
|------|-------|----------|
| CustomVoice | 1.7B-CustomVoice | Voice design with emotion/style control |
| Base | 1.7B-Base | Voice cloning from reference audio |
| VoiceDesign | 1.7B-CustomVoice | Describe a voice to generate |

## Models

- `Qwen/Qwen3-TTS-12Hz-1.7B-CustomVoice` — Voice design, emotion control
- `Qwen/Qwen3-TTS-12Hz-1.7B-Base` — Voice cloning from reference audio
- `Qwen/Qwen3-TTS-12Hz-0.6B-Base` — Smaller base model (used for fine-tuning)

## Dependencies

Managed by `uv`. Client dep: `httpx`. Training deps (optional): `qwen-tts`, `transformers`, `torch`.

## Training Pipeline

```bash
# 1. Record voice samples
uv run scripts/record_voice.py

# 2. Prepare training data (encode audio to codes)
bash scripts/prepare_data.sh input.jsonl prepared.jsonl

# 3. Fine-tune
bash scripts/train.sh prepared.jsonl speaker_name
```
