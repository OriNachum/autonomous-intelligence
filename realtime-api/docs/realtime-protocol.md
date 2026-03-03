# Realtime Protocol

The Realtime API implements a subset of the [OpenAI Realtime API](https://platform.openai.com/docs/api-reference/realtime) protocol over WebSocket. Any client compatible with that protocol can connect to this bridge and use local TTS/STT services transparently.

## Connection

```
WebSocket: ws://localhost:8080/v1/realtime?model=optional-model-name
Subprotocol: realtime
```

The `model` query parameter is optional and currently informational.

On connection, the server sends a `session.created` event with the default session configuration:

```json
{
  "event_id": "event_abc123...",
  "type": "session.created",
  "session": {
    "id": "sess_def456...",
    "object": "realtime.session",
    "modalities": ["text", "audio"],
    "instructions": "",
    "voice": "Mia.Calm",
    "input_audio_format": "pcm16",
    "output_audio_format": "pcm16",
    "temperature": 0.8,
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

## Client Events (Client → Server)

### session.update

Update session configuration. Partial updates are supported.

```json
{
  "type": "session.update",
  "session": {
    "instructions": "You are a helpful assistant.",
    "voice": "alloy",
    "temperature": 0.7,
    "turn_detection": {
      "type": "server_vad",
      "threshold": 0.6,
      "silence_duration_ms": 500,
      "prefix_padding_ms": 200,
      "aec_mode": "aec"
    }
  }
}
```

Set `turn_detection` to `null` for manual mode (push-to-talk).

Server responds with `session.updated`.

### input_audio_buffer.append

Send audio data to the server. Audio accumulates until committed.

```json
{
  "type": "input_audio_buffer.append",
  "audio": "<base64-encoded PCM16 24kHz mono>"
}
```

In server_vad mode, the VAD processes each chunk automatically and may emit `speech_started`, `speech_stopped`, and auto-commit.

### input_audio_buffer.commit

Manually commit the audio buffer for processing (manual mode).

```json
{
  "type": "input_audio_buffer.commit"
}
```

Triggers the STT → LLM → TTS pipeline. Server responds with `input_audio_buffer.committed`.

### input_audio_buffer.clear

Discard all buffered audio and reset VAD state.

```json
{
  "type": "input_audio_buffer.clear"
}
```

Server responds with `input_audio_buffer.cleared`.

### response.create

Request a response generation. Can include text input for text-based conversations.

```json
{
  "type": "response.create",
  "response": {
    "input": [
      {
        "type": "message",
        "role": "user",
        "content": [
          {"type": "input_text", "text": "Hello, how are you?"}
        ]
      }
    ]
  }
}
```

If no input is provided, generates a response based on the existing conversation history.

### response.cancel

Cancel the current response generation.

```json
{
  "type": "response.cancel"
}
```

Stops LLM streaming and TTS synthesis. The response is finalized with `status: "cancelled"`.

## Server Events (Server → Client)

### Session Events

**session.created** — Sent on connection:
```json
{
  "event_id": "event_...",
  "type": "session.created",
  "session": { ... }
}
```

**session.updated** — After config change:
```json
{
  "event_id": "event_...",
  "type": "session.updated",
  "session": { ... }
}
```

### Input Audio Buffer Events

**input_audio_buffer.committed** — Audio committed for processing:
```json
{
  "event_id": "event_...",
  "type": "input_audio_buffer.committed",
  "item_id": "item_..."
}
```

**input_audio_buffer.cleared** — Buffer cleared:
```json
{
  "event_id": "event_...",
  "type": "input_audio_buffer.cleared"
}
```

**input_audio_buffer.speech_started** — VAD detected speech onset:
```json
{
  "event_id": "event_...",
  "type": "input_audio_buffer.speech_started",
  "audio_start_ms": 1234
}
```

**input_audio_buffer.speech_stopped** — VAD detected speech end:
```json
{
  "event_id": "event_...",
  "type": "input_audio_buffer.speech_stopped",
  "audio_end_ms": 5678
}
```

### Transcription Events

**conversation.item.input_audio_transcription.completed** — STT result:
```json
{
  "event_id": "event_...",
  "type": "conversation.item.input_audio_transcription.completed",
  "item_id": "item_...",
  "content_index": 0,
  "transcript": "What is the weather today?"
}
```

### Response Lifecycle Events

**response.created** — Response generation started:
```json
{
  "event_id": "event_...",
  "type": "response.created",
  "response": {
    "id": "resp_...",
    "object": "realtime.response",
    "status": "in_progress",
    "output": []
  }
}
```

**response.done** — Response complete:
```json
{
  "event_id": "event_...",
  "type": "response.done",
  "response": {
    "id": "resp_...",
    "object": "realtime.response",
    "status": "completed",
    "output": [{ ... }]
  }
}
```

Status is `"completed"` or `"cancelled"`.

### Output Item Events

**response.output_item.added** — New output item in the response:
```json
{
  "event_id": "event_...",
  "type": "response.output_item.added",
  "response_id": "resp_...",
  "output_index": 0,
  "item": {
    "id": "item_...",
    "object": "realtime.item",
    "type": "message",
    "role": "assistant",
    "content": []
  }
}
```

**response.output_item.done** — Item finished.

### Content Part Events

**response.content_part.added** — New content part (audio or transcript):
```json
{
  "event_id": "event_...",
  "type": "response.content_part.added",
  "response_id": "resp_...",
  "item_id": "item_...",
  "output_index": 0,
  "content_index": 0,
  "part": {"type": "audio", "audio": ""}
}
```

Content parts:
- Index 0: `type: "audio"` — Audio data
- Index 1: `type: "audio_transcript"` — Text transcript

**response.content_part.done** — Part finished.

### Audio Stream Events

**response.audio.delta** — Audio data chunk:
```json
{
  "event_id": "event_...",
  "type": "response.audio.delta",
  "response_id": "resp_...",
  "item_id": "item_...",
  "output_index": 0,
  "content_index": 0,
  "delta": "<base64-encoded PCM16 24kHz>"
}
```

**response.audio.done** — Audio stream finished.

### Transcript Stream Events

**response.audio_transcript.delta** — Text delta:
```json
{
  "event_id": "event_...",
  "type": "response.audio_transcript.delta",
  "response_id": "resp_...",
  "item_id": "item_...",
  "output_index": 0,
  "content_index": 1,
  "delta": "The weather today is sunny. "
}
```

Transcript deltas arrive at sentence granularity — each delta contains one complete sentence plus a trailing space.

**response.audio_transcript.done** — Full transcript:
```json
{
  "event_id": "event_...",
  "type": "response.audio_transcript.done",
  "response_id": "resp_...",
  "item_id": "item_...",
  "output_index": 0,
  "content_index": 1,
  "transcript": "The weather today is sunny. High of 75 degrees."
}
```

### Error Events

```json
{
  "event_id": "event_...",
  "type": "error",
  "error": {
    "type": "server_error",
    "message": "STT transcription failed",
    "code": null
  }
}
```

## Event Sequence — Typical Turn

```
Client                          Server
  │                               │
  │ input_audio_buffer.append     │
  │──────────────────────────────→│
  │ input_audio_buffer.append     │
  │──────────────────────────────→│
  │                               │ (VAD detects speech)
  │                               │
  │      speech_started           │
  │←──────────────────────────────│
  │                               │
  │ input_audio_buffer.append     │
  │──────────────────────────────→│
  │ ...more audio...              │
  │──────────────────────────────→│
  │                               │ (VAD detects silence)
  │                               │
  │      speech_stopped           │
  │←──────────────────────────────│
  │      committed                │
  │←──────────────────────────────│
  │                               │
  │                               │ (STT runs)
  │  transcription.completed      │
  │←──────────────────────────────│
  │                               │
  │                               │ (LLM starts streaming)
  │  response.created             │
  │←──────────────────────────────│
  │  output_item.added            │
  │←──────────────────────────────│
  │  content_part.added (audio)   │
  │←──────────────────────────────│
  │  content_part.added (text)    │
  │←──────────────────────────────│
  │                               │
  │  audio_transcript.delta       │ ← First sentence text
  │←──────────────────────────────│
  │  audio.delta                  │ ← First sentence audio chunk 1
  │←──────────────────────────────│
  │  audio.delta                  │ ← First sentence audio chunk 2
  │←──────────────────────────────│
  │  ...                          │
  │  audio_transcript.delta       │ ← Second sentence text
  │←──────────────────────────────│
  │  audio.delta                  │ ← Second sentence audio chunks
  │←──────────────────────────────│
  │  ...                          │
  │                               │
  │  audio.done                   │
  │←──────────────────────────────│
  │  audio_transcript.done        │
  │←──────────────────────────────│
  │  content_part.done            │
  │←──────────────────────────────│
  │  output_item.done             │
  │←──────────────────────────────│
  │  response.done                │
  │←──────────────────────────────│
```

## Audio Format

All audio in the protocol is:
- **PCM16** (16-bit signed little-endian)
- **24,000 Hz** sample rate
- **Mono** (single channel)
- **Base64-encoded** for transport over JSON/WebSocket

Each sample is 2 bytes, so 1 second of audio = 48,000 bytes raw = ~64,000 bytes base64.

## ID Conventions

All IDs are generated server-side using UUID hex:

| Prefix | Type | Example |
|--------|------|---------|
| `event_` | Event ID | `event_a1b2c3d4e5f6...` |
| `sess_` | Session ID | `sess_f7e8d9c0b1a2...` |
| `item_` | Conversation item | `item_1a2b3c4d5e6f...` |
| `resp_` | Response | `resp_7f8e9d0c1b2a...` |
| `part_` | Content part | `part_3c4d5e6f7a8b...` |

## Differences from OpenAI's Realtime API

This implementation is a compatible subset with some extensions:

**Supported:**
- Session management (create, update)
- Audio input streaming with server VAD
- Manual commit mode
- Response generation with streaming audio + transcript
- Response cancellation
- Error events

**Extensions (not in OpenAI's API):**
- `aec_mode` field in turn_detection config
- Intelligent barge-in with LLM decision (transparent to client)
- Direct Magpie voice names accepted alongside OpenAI names

**Not implemented:**
- Function/tool calling
- Conversation item CRUD (create, delete, truncate)
- Input audio transcription model selection
- Multiple output items per response
- Rate limiting events
- `conversation.item.created` events (items are tracked server-side)
