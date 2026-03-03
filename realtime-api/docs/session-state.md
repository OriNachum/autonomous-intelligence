# Session State and Parallel Calling

Each WebSocket connection to `/v1/realtime` creates an independent `Session` object that manages all state for that conversation. Multiple clients can connect simultaneously, each with their own isolated session.

## Session Lifecycle

```
WebSocket connect
    │
    ▼
Session created (unique ID)
    │
    ├── session.created event sent to client
    ├── VAD initialized (if server_vad)
    ├── Sender task started (queue → WebSocket)
    │
    ▼
Event loop (receive → dispatch → process)
    │
    ├── session.update → reconfigure
    ├── input_audio_buffer.append → buffer + VAD
    ├── input_audio_buffer.commit → pipeline
    ├── response.create → generate
    ├── response.cancel → stop
    │
    ▼
WebSocket disconnect
    │
    ├── Cancel event set
    ├── Sender task cancelled
    ├── Response task cancelled (if running)
    │
    ▼
Session destroyed
```

## Session Object

```python
class Session:
    id: str                              # "sess_<hex24>" — unique session identifier
    config: SessionConfig                # Voice, modalities, turn detection, etc.
    conversation: Conversation           # Message history
    audio_buffer: AudioBuffer            # Incoming audio accumulator
    send_queue: asyncio.Queue[dict]      # Events waiting to be sent to client
    cancel_event: asyncio.Event          # Signal to stop current response
    is_speaking: bool                    # True during TTS playback
    current_response_text: str           # Accumulates assistant text (for barge-in)
    _vad: ServerVAD | None               # VAD instance (None if manual mode)
    _response_task: asyncio.Task | None  # Current response generation task
```

## Session Configuration

The `SessionConfig` holds all per-session settings:

```python
@dataclass
class SessionConfig:
    modalities: list[str]          # ["text", "audio"] or ["text"]
    instructions: str              # System prompt
    voice: str                     # TTS voice name
    input_audio_format: str        # "pcm16"
    output_audio_format: str       # "pcm16"
    temperature: float             # LLM temperature (0.0-2.0)
    turn_detection: TurnDetectionConfig | None  # VAD config or None (manual)
```

All settings can be updated at any time via `session.update`:

```json
{
  "type": "session.update",
  "session": {
    "instructions": "You are a helpful cooking assistant.",
    "voice": "Aria.Happy",
    "temperature": 0.6,
    "turn_detection": {
      "type": "server_vad",
      "threshold": 0.6,
      "silence_duration_ms": 500,
      "aec_mode": "aec"
    }
  }
}
```

Partial updates are supported — only the fields present in the update are changed.

When `turn_detection` changes, the VAD is re-initialized with the new parameters.

## Conversation History

The `Conversation` class tracks all messages exchanged:

```python
class Conversation:
    _items: list[ConversationItem]

    def add_user_message(text, item_id=None) -> ConversationItem
    def add_assistant_message(text, item_id=None) -> ConversationItem
    def to_chat_messages(system_instructions="") -> list[dict]
```

### Message Format

Each conversation item has:
- `id` — Unique item ID (`"item_<hex24>"`)
- `role` — `"user"` or `"assistant"`
- `content` — List of content parts

User messages use `input_text` type (from transcription):
```json
{"type": "input_text", "text": "What's the weather like?"}
```

Assistant messages use `text` type:
```json
{"type": "text", "text": "The weather today is sunny with a high of 75°F."}
```

### Conversion to Chat Messages

`to_chat_messages()` converts the conversation to OpenAI chat completion format:

```python
[
    {"role": "system", "content": "You are a helpful assistant."},
    {"role": "user", "content": "What's the weather like?"},
    {"role": "assistant", "content": "The weather today is sunny."},
    {"role": "user", "content": "Will it rain tomorrow?"},
]
```

The full history is sent with every LLM call, providing conversation context.

## Audio Buffer

The `AudioBuffer` accumulates audio chunks from the client:

```python
class AudioBuffer:
    def append(audio_b64: str)       # Append base64-encoded audio
    def append_raw(pcm_bytes: bytes) # Append raw PCM16 bytes
    def commit() -> bytes            # Return all data and clear
    def clear()                      # Reset
    is_empty: bool                   # Check if empty
    total_bytes: int                 # Current size
```

In **server_vad mode**, the audio buffer is a backup — the VAD's internal speech buffer is what gets committed. After auto-commit, the main buffer is cleared.

In **manual mode**, the audio buffer is primary — `input_audio_buffer.commit` returns all accumulated audio for processing.

## Concurrent Tasks Per Session

Each session runs multiple async tasks:

### Sender Task
Drains the `send_queue` and writes events to the WebSocket:
```python
async def _sender_loop(ws, session):
    while True:
        event = await session.send_queue.get()
        await ws.send_json(event)
```

### Receiver Task
The main event loop that receives and dispatches client events. Runs in the `handle_realtime_ws` function.

### Response Task
When a pipeline runs (STT → LLM → TTS), it's spawned as an `asyncio.Task`:
```python
session._response_task = asyncio.create_task(_pipeline())
```

Only one response task runs at a time. Starting a new response cancels the existing one:
```python
if session._response_task and not session._response_task.done():
    session.cancel_event.set()
    session._response_task.cancel()
    await session._response_task  # Wait for cleanup
session.cancel_event.clear()
```

### Barge-in Task
AEC mode barge-in evaluations are spawned as independent tasks:
```python
asyncio.create_task(_evaluate_barge_in(session, audio_bytes))
```

## Parallel Sessions

Multiple WebSocket connections run completely independently:

```
Client A ──→ WebSocket ──→ Session A (own VAD, conversation, audio buffer)
Client B ──→ WebSocket ──→ Session B (own VAD, conversation, audio buffer)
Client C ──→ WebSocket ──→ Session C (own VAD, conversation, audio buffer)
```

Each session has:
- Its own `Session` object with isolated state
- Its own async tasks (sender, receiver, response)
- Its own conversation history
- Its own VAD instance with independent model state
- Its own cancel event and speaking flag

Sessions share:
- The FastAPI application instance
- The `settings` singleton (read-only configuration)
- Backend service connections (TTS, STT, LLM) — each HTTP call creates a new `httpx.AsyncClient`

### Scalability Considerations

**CPU**: Each session's VAD runs torch inference on CPU. Silero VAD is lightweight (~3ms per 32ms chunk), so dozens of sessions can share a single CPU core.

**Memory**: Each session holds its conversation history, audio buffer, and VAD state. A typical session uses ~10-50MB depending on conversation length and audio buffer size.

**Backend services**: The TTS and STT services process one request at a time (vLLM `max_inflight: 1`, Parakeet single-model). Multiple concurrent sessions will queue at these backends. For high concurrency, scale the backend services horizontally.

**WebSocket**: FastAPI/Uvicorn handles thousands of concurrent WebSocket connections efficiently via asyncio.

## State Synchronization

The `is_speaking` flag is the critical synchronization point between the response pipeline and VAD:

```python
# Response starts generating audio
session.is_speaking = True

# VAD checks this flag on every chunk
vad.is_speaking = session.is_speaking

# Response finishes
session.is_speaking = False
```

This flag determines:
- Whether the echo gate is active (non-AEC mode)
- Whether barge-in evaluation is triggered (AEC mode)
- Whether VAD events are treated as new turns or interruptions

## Cancel/Interrupt Flow

```
response.cancel OR barge-in STOP
    │
    ├── session.cancel_event.set()
    │
    ├── LLM streaming: checks cancel_event, breaks loop
    ├── TTS streaming: checks cancel_event, breaks loop
    ├── Sentence iteration: checks cancel_event, breaks loop
    │
    ├── session._response_task.cancel() (if still running)
    │
    ├── is_speaking = False
    │
    └── Response finalized with status: "cancelled"
```

The `cancel_event` is an `asyncio.Event` — setting it is instant and all streaming loops check it on their next iteration (typically within milliseconds).
