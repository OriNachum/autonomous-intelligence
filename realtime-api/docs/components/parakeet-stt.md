# Parakeet STT Service

NVIDIA Parakeet-based automatic speech recognition (ASR) service.

| Property | Value |
|----------|-------|
| Model | `nvidia/parakeet-tdt-0.6b-v2` |
| Port | `9002` |
| Health endpoint | `GET /v1/health/ready` |
| API endpoint | `POST /v1/audio/transcriptions` |
| Build context | `../qwen3-tts/Dockerfile.parakeet` |

The service is built from a custom Dockerfile and downloads the Parakeet model from HuggingFace on first startup.

---

## Endpoint

### `POST /v1/audio/transcriptions`

**Request:** `multipart/form-data`

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `file` | binary | Yes | Audio file (WAV recommended) |
| `language` | string | No | Language code (default: `en`) |

**Response:** JSON

```json
{
  "text": "Hello, how are you today?"
}
```

---

## Curl Examples

### Transcribe an audio file

```bash
curl -X POST http://localhost:9002/v1/audio/transcriptions \
  -F "file=@recording.wav" \
  -F "language=en"
```

### Record and transcribe in one line

```bash
arecord -d 5 -r 16000 -f S16_LE -c 1 /tmp/rec.wav && \
curl -X POST http://localhost:9002/v1/audio/transcriptions \
  -F "file=@/tmp/rec.wav" \
  -F "language=en"
```

### Transcribe with verbose output

```bash
curl -s -X POST http://localhost:9002/v1/audio/transcriptions \
  -F "file=@recording.wav" \
  -F "language=en" | python3 -m json.tool
```

### Transcribe from a specific device (e.g., ReSpeaker)

```bash
arecord -D plughw:1,0 -d 5 -r 16000 -f S16_LE -c 1 /tmp/rec.wav && \
curl -X POST http://localhost:9002/v1/audio/transcriptions \
  -F "file=@/tmp/rec.wav" \
  -F "language=en"
```

---

## Audio Format

**Recommended input:** 16 kHz, 16-bit PCM, mono WAV

The service accepts audio at any sample rate — it resamples internally. However, 16 kHz is optimal since the Parakeet model operates at 16 kHz.

The bridge (`stt_client.py`) receives 24 kHz PCM16 from the WebSocket client, resamples it to 16 kHz, and wraps it in a WAV container before sending to Parakeet:

```
Client audio (24kHz PCM16) → resample to 16kHz → WAV container → POST to Parakeet
```

---

## Performance

Approximate transcription latency on DGX Spark (GPU):

| Audio duration | Latency | Notes |
|---------------|---------|-------|
| 1 second | ~100 ms | Single short utterance |
| 3 seconds | ~150 ms | Typical voice command |
| 10 seconds | ~300 ms | Longer speech segment |
| 30 seconds | ~500 ms | Extended monologue |

Latency scales sub-linearly — the model processes in chunks. First request after startup may be slower due to model warmup.

---

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `PARAKEET_PORT` | `9002` | HTTP port for the STT service |
| `PARAKEET_MODEL` | `nvidia/parakeet-tdt-0.6b-v2` | HuggingFace model ID |
| `HF_HOME` | `/root/.cache/huggingface` | Model cache directory (mapped to `hf-cache` volume) |
| `STT_URL` | `http://parakeet-stt:9002` | URL the bridge uses to reach Parakeet |
