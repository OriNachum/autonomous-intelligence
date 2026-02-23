# Local Models

Every ML model in the Realtime API stack runs locally — no cloud API calls for TTS or STT. The LLM backend is configurable and can also be local.

## Magpie TTS (Qwen3-TTS)

**Model**: `Qwen/Qwen3-TTS-12Hz-1.7B-CustomVoice`
**Parameters**: 1.7 billion
**Architecture**: Two-stage autoregressive pipeline served via vLLM-Omni

### Pipeline Stages

**Stage 0 — Talker** (Text → Speech Codes):
- Architecture: `Qwen3TTSTalkerForConditionalGeneration`
- Worker type: Autoregressive (AR)
- Max sequence length: 4,096 tokens
- GPU memory: 15% of available
- Sampling: temperature=0.3, top_k=50, top_p=0.85
- Output: Latent speech codes (stop token: 2150)

**Stage 1 — Code2Wav** (Speech Codes → Audio):
- Architecture: `Qwen3TTSCode2Wav`
- Worker type: Generation
- Max sequence length: 32,768 tokens
- GPU memory: 15% of available
- Sampling: temperature=0.0 (deterministic), seed=42
- Output: Raw audio at 22,050 Hz

The two stages communicate via shared memory connector with codec streaming. Audio is generated in 25-frame chunks, enabling real-time streaming output — the client starts receiving audio before the full sentence is synthesized.

### Voices

Available Magpie voices use the prefix `Magpie-Multilingual.EN-US.`:

| Voice | Emotions |
|-------|----------|
| Mia | Neutral, Calm, Angry, Happy, Sad |
| Aria | Neutral, Calm, Angry, Happy, Sad, Fearful |
| Jason | Neutral, Calm, Angry, Happy |
| Leo | Neutral, Calm, Angry, Sad, Fearful |

OpenAI Realtime API voice names are mapped to Magpie equivalents:

| OpenAI Voice | Magpie Voice |
|-------------|-------------|
| alloy | Mia.Calm |
| echo | Jason.Neutral |
| fable | Aria.Calm |
| onyx | Leo.Calm |
| nova | Mia.Happy |
| shimmer | Aria.Happy |

Direct Magpie voice names (e.g., `Mia.Happy`) are also accepted and passed through.

### SSML Speed Control

When `tts_speed != 100`, text is wrapped in SSML prosody:

```xml
<speak><prosody rate="125%">Hello, how can I help?</prosody></speak>
```

Default speed is 125% (slightly faster than normal speech).

### Streaming API

The TTS service exposes `POST /v1/audio/synthesize_online` for streaming synthesis:
- Input: text, language, voice name, encoding format, sample rate
- Output: Chunked raw PCM16 at 22,050 Hz
- The bridge resamples to 24,000 Hz before sending to the client

Non-streaming endpoint `POST /v1/audio/synthesize` also available but not used by the bridge.

## Parakeet STT (NeMo ASR)

**Model**: `nvidia/parakeet-tdt-0.6b-v2`
**Parameters**: 600 million
**Framework**: NVIDIA NeMo
**Architecture**: TDT (Token-and-Duration Transducer)

### API

`POST /v1/audio/transcriptions` — Riva-compatible endpoint:
- Input: WAV file upload (multipart/form-data), language parameter
- Output: JSON `{"text": "transcribed text"}`
- Accepts any sample rate (internal resampling to 16kHz via scipy)
- Handles mono and stereo (stereo averaged to mono)

`GET /v1/health/ready` — Health check, returns `{"status": "ready"}`

### Audio Preprocessing

The bridge converts client audio before sending to Parakeet:

```
Client PCM16 24kHz → resample to 16kHz → wrap as WAV → POST to Parakeet
```

Resampling uses `scipy.signal.resample` with int16 clipping to prevent overflow.

### Performance

Parakeet TDT 0.6B is lightweight and fast:
- Short utterances (1-3 seconds): ~100-200ms transcription time
- Full sentences (5-10 seconds): ~300-500ms
- The model runs on GPU with NeMo's optimized inference

## LLM Backend

The bridge connects to any OpenAI-compatible chat completion endpoint.

### Configuration

| Variable | Default | Description |
|----------|---------|-------------|
| `OPENAI_BASE_URL` | `http://host.docker.internal:8000` | Base URL for `/v1/chat/completions` |
| `OPENAI_API_KEY` | `EMPTY` | Bearer token (omitted if "EMPTY") |
| `OPENAI_MODEL` | `default` | Model name in API requests |

### Streaming

The LLM client uses standard OpenAI SSE streaming:
- `POST /v1/chat/completions` with `stream: true`
- Parses `data: {...}` lines, extracts `choices[0].delta.content`
- Terminates on `data: [DONE]`

Text deltas are buffered and split into sentences at `.!?` boundaries for TTS pipelining.

### Compatible Backends

Any server implementing the OpenAI chat completions API works:
- **vLLM** (recommended for local): `vllm serve <model>`
- **llama.cpp** with OpenAI-compatible server
- **text-generation-inference** (TGI)
- **Ollama** with OpenAI compatibility mode
- **OpenAI API** itself (set real `OPENAI_API_KEY`)

### Barge-in Decision Model

A separate LLM call is used for intelligent barge-in evaluation:
- `max_tokens=1`, `temperature=0`, `stream=false`
- Optionally uses a different (faster) model via `BARGE_IN_MODEL`
- Defaults to the main model if not configured
- Timeout: 10 seconds (fast decision required)

## Model Caching

All models are cached in a shared Docker volume:

```yaml
volumes:
  hf-cache:
```

Mounted at `/root/.cache/huggingface` in both GPU services. First startup downloads models from HuggingFace Hub (~5-10GB). Subsequent startups load from cache.

The Parakeet model is additionally pre-downloaded during Docker build (`Dockerfile.parakeet` runs `from_pretrained()` at build time), so the container is ready immediately after starting.

## Sample Rate Matrix

| Component | Sample Rate | Format |
|-----------|------------|--------|
| Client (WebSocket) | 24,000 Hz | PCM16 little-endian, base64 |
| Silero VAD | 16,000 Hz | Float32, 512-sample chunks |
| Parakeet STT | 16,000 Hz | WAV file |
| Magpie TTS output | 22,050 Hz | Raw PCM16 stream |

All resampling is handled transparently by `audio.py` using scipy.
