# Magpie TTS Service

NVIDIA NIM-based multilingual text-to-speech service.

| Property | Value |
|----------|-------|
| Image | `nvcr.io/nim/nvidia/magpie-tts-multilingual:latest` |
| Port | `9000` |
| Health endpoint | `GET /v1/health/ready` |
| Streaming endpoint | `POST /v1/audio/synthesize_online` |
| Batch endpoint | `POST /v1/audio/synthesize` |
| Output format | PCM16 Linear at configurable sample rate |

---

## Voices & Emotions

Four speakers, each with multiple emotion variants:

| Speaker | Neutral | Calm | Angry | Happy | Sad | Fearful |
|---------|---------|------|-------|-------|-----|---------|
| **Mia** (female) | Mia.Neutral | Mia.Calm | Mia.Angry | Mia.Happy | Mia.Sad | — |
| **Aria** (female) | Aria.Neutral | Aria.Calm | Aria.Angry | Aria.Happy | Aria.Sad | Aria.Fearful |
| **Jason** (male) | Jason.Neutral | Jason.Calm | Jason.Angry | Jason.Happy | — | — |
| **Leo** (male) | Leo.Neutral | Leo.Calm | Leo.Angry | — | Leo.Sad | Leo.Fearful |

Using just the base name (e.g., `Mia`) defaults to the neutral variant.

All voice names are prefixed with `Magpie-Multilingual.EN-US.` when sent to the API. The bridge and CLI tool handle this automatically.

---

## OpenAI → Magpie Voice Mapping

The bridge maps OpenAI Realtime API voice names to Magpie voices:

| OpenAI voice | Magpie voice | Character |
|--------------|-------------|-----------|
| `alloy` | Mia.Calm | Female, calm |
| `echo` | Jason.Neutral | Male, neutral |
| `fable` | Aria.Calm | Female, calm |
| `onyx` | Leo.Calm | Male, calm |
| `nova` | Mia.Happy | Female, happy |
| `shimmer` | Aria.Happy | Female, happy |

You can also pass Magpie voice names directly (e.g., `Leo.Fearful`).

---

## Endpoints

### Streaming: `POST /v1/audio/synthesize_online`

Returns audio as a chunked stream — ideal for real-time playback. The bridge uses this endpoint.

**Request:** `multipart/form-data`

| Field | Type | Description |
|-------|------|-------------|
| `text` | string | Text to speak (plain text or SSML) |
| `voice` | string | Full voice name (e.g., `Magpie-Multilingual.EN-US.Mia.Calm`) |
| `language` | string | Language code (e.g., `en-US`) |
| `encoding` | string | `LINEAR_PCM` |
| `sample_rate_hz` | string | Output sample rate (e.g., `22050`) |

**Response:** Chunked binary stream of raw PCM16 audio.

### Batch: `POST /v1/audio/synthesize`

Returns complete audio in one response — simpler for scripts and testing.

**Request:** Same fields as streaming endpoint.

**Response:** Complete WAV audio file.

---

## Curl Examples

### Streaming synthesis (raw PCM)

```bash
curl -X POST http://localhost:9000/v1/audio/synthesize_online \
  -F "text=Hello, how are you today?" \
  -F "voice=Magpie-Multilingual.EN-US.Mia.Calm" \
  -F "language=en-US" \
  -F "encoding=LINEAR_PCM" \
  -F "sample_rate_hz=22050" \
  --output speech.pcm
```

Play with:
```bash
aplay -r 22050 -f S16_LE -c 1 speech.pcm
```

### Batch synthesis (WAV)

```bash
curl -X POST http://localhost:9000/v1/audio/synthesize \
  -F "text=Hello, how are you today?" \
  -F "voice=Magpie-Multilingual.EN-US.Mia.Calm" \
  -F "language=en-US" \
  --output speech.wav
```

Play with:
```bash
aplay speech.wav
```

### With SSML speed control

```bash
curl -X POST http://localhost:9000/v1/audio/synthesize \
  -F 'text=<speak><prosody rate="125%">This is faster speech.</prosody></speak>' \
  -F "voice=Magpie-Multilingual.EN-US.Aria.Happy" \
  -F "language=en-US" \
  --output fast_speech.wav
```

### Different voices

```bash
# Angry Leo
curl -X POST http://localhost:9000/v1/audio/synthesize \
  -F "text=I cannot believe this happened!" \
  -F "voice=Magpie-Multilingual.EN-US.Leo.Angry" \
  -F "language=en-US" \
  --output angry.wav

# Fearful Aria
curl -X POST http://localhost:9000/v1/audio/synthesize \
  -F "text=Did you hear that noise?" \
  -F "voice=Magpie-Multilingual.EN-US.Aria.Fearful" \
  -F "language=en-US" \
  --output fearful.wav
```

---

## SSML Speed Control

Wrap text in SSML `<prosody>` tags to control speech rate:

```xml
<speak><prosody rate="125%">This text is 25 percent faster.</prosody></speak>
```

The bridge applies this automatically based on the `TTS_SPEED` env var (default: `125`%).

Speed values:
- `100` — normal speed
- `125` — 25% faster (default in bridge)
- `150` — 50% faster
- `75` — 25% slower

---

## CLI Tool

The `speak.py` script provides a quick way to test TTS from the command line:

```bash
# Basic usage
uv run scripts/speak.py --message "Hello world"

# With voice selection
uv run scripts/speak.py --message "Great news!" --voice Mia.Happy

# With speed control
uv run scripts/speak.py --message "Slow down" --voice Aria --speed 80

# Custom server URL
uv run scripts/speak.py --message "Hi" --server-url http://192.168.1.100:9000
```

The CLI uses the batch endpoint (`/v1/audio/synthesize`) and plays audio via `aplay`.

---

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `NGC_API_KEY` | _(required)_ | NVIDIA NGC API key for NIM container authentication |
| `MAGPIE_TTS_PORT` | `9000` | HTTP port for the TTS service |
| `DEFAULT_VOICE` | `Mia.Calm` | Default voice used by the bridge |
| `TTS_SPEED` | `125` | Default speech speed percentage (SSML prosody rate) |
| `TTS_URL` | `http://magpie-tts:9000` | URL the bridge uses to reach Magpie TTS |
