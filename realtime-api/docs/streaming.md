# Streaming Architecture

The Realtime API is built around bidirectional streaming at every layer — audio in, text generation, and audio out all flow concurrently. This minimizes latency and enables a real-time conversational experience.

## End-to-End Flow

```
Client (WebSocket)
    │ input_audio_buffer.append (base64 PCM16 24kHz)
    │ ↓ continuous stream
    │
    ▼
┌─────────────────────────────────────────┐
│ realtime-api bridge                      │
│                                          │
│  Audio Buffer ──→ VAD (16kHz)            │
│       │              │                   │
│       │         speech_stopped           │
│       ▼              │                   │
│  PCM16 24kHz ────────┘                   │
│       │                                  │
│       ▼                                  │
│  Parakeet STT (16kHz WAV) ──→ text       │
│       │                                  │
│       ▼                                  │
│  LLM streaming ──→ sentence buffer       │
│       │                                  │
│       ▼ (per sentence)                   │
│  Magpie TTS batch (22050Hz PCM16)         │
│       │                                  │
│       ▼                                  │
│  Resample 22050→24kHz ──→ base64         │
│       │                                  │
└───────┼──────────────────────────────────┘
        │
        ▼ response.audio.delta (base64 PCM16 24kHz)
    Client (WebSocket)
```

## Streaming Layers

### 1. Audio Input Streaming

The client sends audio continuously via `input_audio_buffer.append` events:

```json
{
  "type": "input_audio_buffer.append",
  "audio": "<base64-encoded PCM16 24kHz>"
}
```

Each chunk is:
- Appended to the session's `AudioBuffer`
- Fed to the VAD (if server_vad enabled)
- Processed in 32ms windows (512 samples at 16kHz after resampling)

There is no batching or buffering delay — each chunk is processed as it arrives.

### 2. VAD Streaming

The Silero VAD processes audio in a streaming fashion:

```python
vad_events = vad.process_chunk(pcm_bytes)
```

The VAD maintains internal recurrent state across chunks, so it tracks speech probability over time. It handles partial chunks via a residual buffer — if a client sends 1000 bytes but the VAD chunk size maps to 960 bytes, the remaining 40 bytes are prepended to the next call.

VAD events are emitted immediately:
- `speech_started` — As soon as 3 consecutive chunks exceed the threshold
- `speech_stopped` — After 600ms of silence below threshold

### 3. LLM Text Streaming

Chat completions are streamed via Server-Sent Events (SSE):

```
POST /v1/chat/completions
Content-Type: application/json

{"model": "...", "messages": [...], "stream": true}
```

Response:
```
data: {"choices":[{"delta":{"content":"Hello"}}]}
data: {"choices":[{"delta":{"content":","}}]}
data: {"choices":[{"delta":{"content":" how"}}]}
...
data: [DONE]
```

Text deltas are accumulated and split into sentences at `.!?` boundaries using the regex `(?<=[.!?])\s+`. In loose mode (buffer > 200 chars), the splitter also breaks at em-dash `—`, en-dash `–`, and spaced hyphen ` - `.

### 4. Sentence-Level TTS Pipelining

This is the key optimization. Instead of waiting for the complete LLM response before starting TTS, each sentence is sent to TTS as soon as it's complete:

```python
async for sentence in stream_sentences(messages, cancel_event=cancel_event):
    # Emit transcript delta immediately
    await session.send(response_audio_transcript_delta(..., sentence))

    # Batch TTS for this sentence — returns full PCM bytes
    tts_pcm = await synthesize(sentence, voice=..., cancel_event=cancel_event)
    resampled = resample_pcm16(tts_pcm, TTS_SAMPLE_RATE, CLIENT_SAMPLE_RATE)

    # Chunk into 100ms base64 frames
    chunk_bytes = CLIENT_SAMPLE_RATE // 10 * 2  # 4800 bytes per 100ms
    for offset in range(0, len(resampled), chunk_bytes):
        chunk_b64 = base64.b64encode(resampled[offset:offset + chunk_bytes]).decode()
        await session.send(response_audio_delta(..., chunk_b64))
```

This means:
- The first audio reaches the client as soon as the first sentence is synthesized
- Subsequent sentences overlap with LLM generation
- The user hears audio while the LLM is still generating later sentences

### 5. TTS Audio Delivery

The bridge calls the Magpie TTS **batch** endpoint and reads the full response body:

```python
resp = await client.post(url, data={...})
pcm_data = resp.content  # complete PCM16 at 22050Hz
```

The full PCM bytes are then:
1. Resampled from 22050 Hz to 24000 Hz
2. Sliced into 100 ms frames (4800 bytes each)
3. Base64-encoded and sent as `response.audio.delta` WebSocket events

Text longer than 800 characters is split into chunks at natural break points (`, ` then ` `). Each chunk is synthesized separately. A truncation detector retries with a fresh HTTP connection if the audio duration is suspiciously short relative to the text length.

### 6. WebSocket Output Streaming

All server events flow through an async queue:

```python
# Producer (pipeline tasks)
await session.send_queue.put(event)

# Consumer (sender loop)
async def _sender_loop(ws, session):
    while True:
        event = await session.send_queue.get()
        await ws.send_json(event)
```

This decouples event production from WebSocket I/O — the pipeline never blocks on slow network writes.

## Latency Breakdown

For a typical user utterance:

| Phase | Latency | Cumulative |
|-------|---------|------------|
| VAD speech_stopped detection | ~600ms silence | 600ms |
| Parakeet STT transcription | ~200-500ms | ~1s |
| LLM first token | ~200-500ms | ~1.5s |
| LLM first sentence complete | ~500-1000ms | ~2s |
| Magpie TTS first audio chunk | ~200-400ms | ~2.4s |
| Resampling + base64 + WebSocket | ~5ms | ~2.4s |

**Time to first audio: ~2-3 seconds** from end of speech.

The perceived latency is lower because:
- VAD pre-roll captures 300ms before speech onset (user doesn't lose the start of their sentence)
- TTS streaming means audio starts before the full sentence is synthesized
- Sentence pipelining means second and subsequent sentences have near-zero additional latency

## Cancellation

All streaming operations respect `session.cancel_event`:

```python
# LLM streaming
async for delta in stream_chat_completion(...):
    if cancel_event and cancel_event.is_set():
        break

# TTS synthesis (checked before each batch call in _synthesize_single)
if cancel_event and cancel_event.is_set():
    return b""

# Audio chunk sending (checked between 100ms frame sends)
for offset in range(0, len(resampled), chunk_bytes):
    if session.cancel_event.is_set():
        break

# Sentence iteration
async for sentence in stream_sentences(..., cancel_event=cancel_event):
    if session.cancel_event.is_set():
        break
```

When `response.cancel` is received or a barge-in STOP is decided:
1. `cancel_event` is set
2. All streaming loops break on their next iteration
3. The response is finalized with `status: "cancelled"`
4. Resources are freed for the next response

## Concurrent Transcript + Audio

The client receives two parallel streams for each response:
- `response.audio_transcript.delta` — Text of what the assistant is saying
- `response.audio.delta` — Base64-encoded audio

This allows clients to:
- Display real-time captions while audio plays
- Show a text fallback if audio playback fails
- Log the conversation transcript

Both streams are synchronized at the sentence level — a transcript delta is emitted just before the corresponding audio deltas for that sentence.

## Backpressure

The system handles backpressure through:
- **asyncio.Queue** — The send queue buffers events if the WebSocket is temporarily slow
- **TTS concurrency gate** — A semaphore limits parallel TTS requests (default 1), preventing overload
- **VAD residual buffer** — Unprocessed audio bytes carry over to the next chunk

There is no explicit flow control protocol — the assumption is that WebSocket bandwidth (base64 PCM16 at 24kHz = ~96KB/s raw, ~128KB/s base64) is well within typical network capacity.
