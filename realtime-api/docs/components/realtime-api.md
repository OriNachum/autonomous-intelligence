# Realtime API — WebSocket Bridge

FastAPI-based WebSocket bridge that implements the [OpenAI Realtime API](https://platform.openai.com/docs/api-reference/realtime) protocol, connecting a browser/client to local STT, LLM, and TTS services.

| Property | Value |
|----------|-------|
| Port | `8080` |
| Health endpoint | `GET /health` |
| WebSocket endpoint | `ws://localhost:8080/v1/realtime` |
| Subprotocol | `realtime` |
| Build | `Dockerfile` (Python 3.12-slim) |

---

## Connection

Connect via WebSocket with the `realtime` subprotocol:

```javascript
const ws = new WebSocket("ws://localhost:8080/v1/realtime", "realtime");
```

Or with a model query parameter:

```javascript
const ws = new WebSocket("ws://localhost:8080/v1/realtime?model=nvidia/NVIDIA-Nemotron-3-Nano-30B-A3B-FP8", "realtime");
```

On connection, the server sends a `session.created` event with the default session configuration.

---

## Session Configuration

Send a `session.update` event to configure the session:

```json
{
  "type": "session.update",
  "session": {
    "modalities": ["text", "audio"],
    "instructions": "You are a helpful assistant. Be concise.",
    "voice": "alloy",
    "temperature": 0.8,
    "input_audio_format": "pcm16",
    "output_audio_format": "pcm16",
    "turn_detection": {
      "type": "server_vad",
      "threshold": 0.5,
      "silence_duration_ms": 600,
      "prefix_padding_ms": 300,
      "aec_mode": "none"
    }
  }
}
```

### Session Fields

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `modalities` | string[] | `["text", "audio"]` | Enabled modalities |
| `instructions` | string | `""` | System prompt sent to the LLM |
| `voice` | string | `Mia.Calm` | TTS voice (OpenAI name or Magpie name) |
| `temperature` | float | `0.8` | LLM sampling temperature |
| `input_audio_format` | string | `pcm16` | Client → server audio format |
| `output_audio_format` | string | `pcm16` | Server → client audio format |
| `tts_mode` | string | `"whole"` | TTS strategy: `"whole"` (single TTS call for full response) or `"sentence"` (pipelined per-sentence TTS) |
| `turn_detection` | object\|null | `{type: "server_vad", ...}` | VAD config, or `null` for manual mode |

---

## Voice Options

Pass either OpenAI names or Magpie names directly:

**OpenAI names** (mapped automatically):

| Name | Maps to |
|------|---------|
| `alloy` | Mia.Calm |
| `echo` | Jason.Neutral |
| `fable` | Aria.Calm |
| `onyx` | Leo.Calm |
| `nova` | Mia.Happy |
| `shimmer` | Aria.Happy |

**Magpie names** (used directly): `Mia.Calm`, `Aria.Fearful`, `Leo.Angry`, `Jason.Happy`, etc.

See [magpie-tts.md](magpie-tts.md) for the full voices & emotions table.

---

## VAD Tuning

The server runs [Silero VAD](https://github.com/snakers4/silero-vad) on incoming audio to detect speech turns.

| Parameter | Default | Range | Description |
|-----------|---------|-------|-------------|
| `threshold` | `0.5` | 0.0–1.0 | Speech probability threshold. Lower = more sensitive |
| `silence_duration_ms` | `600` | 200–2000 | Silence duration to end a turn (ms) |
| `prefix_padding_ms` | `300` | 0–1000 | Audio to keep before speech start (ms) |
| `aec_mode` | `none` | `none`, `aec` | Acoustic echo cancellation mode |

**Tuning tips:**
- **Noisy environment:** Raise `threshold` to 0.6–0.7
- **Quick responses:** Lower `silence_duration_ms` to 400 (may cut off mid-pause)
- **Deliberate speakers:** Raise `silence_duration_ms` to 1000–1500
- **Missing word starts:** Raise `prefix_padding_ms` to 500

VAD processes audio in 32 ms chunks (512 samples at 16 kHz). Speech is triggered after 3 consecutive chunks above threshold (~96 ms).

---

## Event Flow

```
Client                              Server
  │                                    │
  │──── WebSocket Connect ────────────>│
  │<─── session.created ──────────────│
  │                                    │
  │──── session.update ───────────────>│
  │<─── session.updated ──────────────│
  │                                    │
  │──── input_audio_buffer.append ───>│  (repeated per audio chunk)
  │                                    │
  │<─── input_audio_buffer.            │  (VAD detects speech start)
  │      speech_started ──────────────│
  │                                    │
  │<─── input_audio_buffer.            │  (VAD detects speech end)
  │      speech_stopped ──────────────│
  │                                    │
  │<─── input_audio_buffer.committed ─│  (auto-commit from VAD)
  │                                    │
  │                            ┌───────┤  STT: transcribe audio
  │                            │       │
  │<─── conversation.item.     │       │
  │      input_audio_           │       │
  │      transcription.completed│       │
  │                            │       │
  │                            │  ┌────┤  LLM: stream completion
  │                            │  │    │
  │<─── response.created ─────┘  │    │
  │<─── response.output_item.     │    │
  │      added ────────────────── │    │
  │                               │    │
  │<─── response.audio_transcript.│    │  (per sentence)
  │      delta ───────────────────┤    │
  │<─── response.audio.delta ─────┤    │  TTS: stream audio
  │      (repeat per chunk)       │    │
  │                               │    │
  │<─── response.audio.done ──────┘    │
  │<─── response.audio_transcript.     │
  │      done ─────────────────────────│
  │<─── response.done ────────────────│
  │                                    │
```

---

## Pipeline

```
Audio In ──> VAD ──> STT (Parakeet) ──> LLM (vLLM) ──> TTS (Magpie) ──> Audio Out
  24kHz       16kHz     16kHz WAV         text            22050Hz          24kHz
  PCM16      Silero                    streaming     batch (full response)  PCM16
                                       sentences        resampled         base64
```

1. **Audio In**: Client sends base64-encoded PCM16 at 24 kHz via `input_audio_buffer.append`
2. **VAD**: Silero VAD (resampled to 16 kHz) detects speech start/end
3. **STT**: Parakeet transcribes the captured speech (resampled to 16 kHz WAV)
4. **LLM**: vLLM streams chat completion, split into sentences
5. **TTS**: Magpie synthesizes each sentence (22050 Hz), resampled to 24 kHz
6. **Audio Out**: Server sends base64-encoded PCM16 at 24 kHz via `response.audio.delta`

### Manual Mode

Set `turn_detection: null` in `session.update` to disable VAD. The client then controls turns explicitly:

```json
{"type": "input_audio_buffer.append", "audio": "<base64>"}
{"type": "input_audio_buffer.commit"}
```

### Text-Only Mode

Send text directly via `response.create`:

```json
{
  "type": "response.create",
  "response": {
    "input": [
      {
        "type": "message",
        "role": "user",
        "content": [{"type": "input_text", "text": "What is the weather?"}]
      }
    ]
  }
}
```

---

## Barge-In (AEC Mode)

When `aec_mode: "aec"` is set, the server allows the user to interrupt while the assistant is speaking:

1. VAD continues processing audio during assistant playback (unlike `none` mode which gates it)
2. When speech is detected during playback, the server captures the audio
3. After speech ends, a **barge-in evaluator** runs:
   - Transcribes the captured snippet via STT
   - Sends a fast LLM call: _"Is this a real interruption or just a backchannel (uh-huh, yeah)?"_
   - If **STOP**: cancels the current response and starts a new turn with the captured audio
   - If **CONTINUE**: resumes playback, discards the snippet

The decision window is controlled by `BARGE_IN_WINDOW_MS` (default: 750 ms).

Without AEC (`aec_mode: "none"`), all audio during playback is discarded to prevent echo feedback.

---

## Client Events (→ Server)

| Event | Description |
|-------|-------------|
| `session.update` | Update session configuration |
| `input_audio_buffer.append` | Send audio chunk (`{"audio": "<base64>"}`) |
| `input_audio_buffer.commit` | Manually commit audio buffer for transcription |
| `input_audio_buffer.clear` | Clear the audio buffer and reset VAD |
| `response.create` | Trigger a response (optionally with text input) |
| `response.cancel` | Cancel the current response |

## Server Events (→ Client)

| Event | Description |
|-------|-------------|
| `session.created` | Sent on WebSocket connect |
| `session.updated` | Confirms session config change |
| `input_audio_buffer.committed` | Audio buffer committed (auto or manual) |
| `input_audio_buffer.cleared` | Audio buffer cleared |
| `input_audio_buffer.speech_started` | VAD detected speech start |
| `input_audio_buffer.speech_stopped` | VAD detected speech end |
| `conversation.item.input_audio_transcription.completed` | STT result |
| `response.created` | Response generation started |
| `response.output_item.added` | Output item added to response |
| `response.content_part.added` | Content part added (audio or transcript) |
| `response.audio.delta` | Audio chunk (base64 PCM16 at 24 kHz) |
| `response.audio.done` | Audio stream complete |
| `response.audio_transcript.delta` | Transcript chunk (text) |
| `response.audio_transcript.done` | Full transcript complete |
| `response.content_part.done` | Content part finalized |
| `response.output_item.done` | Output item finalized |
| `response.done` | Response complete (status: `completed` or `cancelled`) |
| `error` | Error with `{type, message, code?}` |

---

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `REALTIME_API_PORT` | `8080` | Published port (host side) |
| `TTS_URL` | `http://magpie-tts:9000` | Magpie TTS service URL |
| `STT_URL` | `http://parakeet-stt:9002` | Parakeet STT service URL |
| `OPENAI_BASE_URL` | `http://vllm-llm:8000` | vLLM service URL |
| `OPENAI_API_KEY` | `EMPTY` | API key for vLLM |
| `OPENAI_MODEL` | `nvidia/NVIDIA-Nemotron-3-Nano-30B-A3B-FP8` | Model name for LLM requests |
| `DEFAULT_VOICE` | `Mia.Calm` | Default TTS voice |
| `TTS_SPEED` | `125` | Default speech speed (%) |
| `DEFAULT_TURN_DETECTION` | `server_vad` | `server_vad` or disable VAD |
| `DEFAULT_AEC_MODE` | `none` | `none` or `aec` |
| `VAD_THRESHOLD` | `0.5` | Speech detection threshold |
| `TTS_CONCURRENCY` | `1` | Max parallel TTS requests (1 = serial) |
| `VAD_SILENCE_MS` | `600` | Silence to end turn (ms) |
| `VAD_PREFIX_PADDING_MS` | `300` | Audio to keep before speech (ms) |
