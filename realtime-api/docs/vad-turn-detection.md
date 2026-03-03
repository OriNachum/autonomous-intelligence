# VAD and Turn Detection

The Realtime API uses Silero VAD (Voice Activity Detection) for automatic turn detection — determining when the user starts and stops speaking. This replaces the need for push-to-talk or manual signaling.

## Two Turn Detection Modes

### Server VAD Mode (Automatic)

The server continuously analyzes incoming audio and automatically detects speech boundaries. The client just streams audio and receives events when turns are detected.

Enable via session update:
```json
{
  "type": "session.update",
  "session": {
    "turn_detection": {
      "type": "server_vad",
      "threshold": 0.5,
      "silence_duration_ms": 600,
      "prefix_padding_ms": 300
    }
  }
}
```

### Manual Mode (Push-to-talk)

The client explicitly signals when a turn is complete by sending `input_audio_buffer.commit`. No VAD processing occurs.

Enable by setting turn_detection to null:
```json
{
  "type": "session.update",
  "session": {
    "turn_detection": null
  }
}
```

In manual mode, the client workflow is:
1. Send `input_audio_buffer.append` events with audio chunks
2. Send `input_audio_buffer.commit` when the user is done speaking
3. The pipeline (STT → LLM → TTS) runs on the committed audio

## Silero VAD

### Model

[Silero VAD](https://github.com/snakers4/silero-vad) is a lightweight neural network for voice activity detection. It runs on CPU via PyTorch and processes 32ms audio chunks.

```python
class SileroVAD:
    def __init__(self):
        model, _ = torch.hub.load("snakers4/silero-vad", "silero_vad", trust_repo=True)
        self.model = model

    def probability(self, float32_samples: np.ndarray) -> float:
        tensor = torch.from_numpy(float32_samples)
        with torch.no_grad():
            return self.model(tensor, 16000).item()
```

**Input requirements:**
- Sample rate: 16,000 Hz
- Format: Float32 normalized to [-1.0, 1.0]
- Chunk size: 512 samples (32ms)
- The model is recurrent — it maintains internal state across chunks

### Audio Preprocessing

Client audio arrives as PCM16 at 24kHz. Before VAD processing:

```
Client PCM16 24kHz → resample to 16kHz → int16 to float32 (/32768) → Silero VAD
```

The resampling and conversion happen inside `ServerVAD.process_chunk()`.

## State Machine

The VAD state machine has two states:

```
         ┌──────────────────────────────────────┐
         │                                      │
         ▼                                      │
    ┌─────────┐    3 chunks > threshold    ┌────────────┐
    │  IDLE   │ ──────────────────────── → │ LISTENING  │
    └─────────┘                            └────────────┘
         ▲                                      │
         │     600ms silence < threshold        │
         └──────────────────────────────────────┘
```

### IDLE State

- Maintains a **pre-roll ring buffer** of recent audio chunks
- Each chunk is checked against the speech threshold
- Tracks consecutive chunks above threshold (`start_count`)
- When `start_count >= 3` (3 × 32ms = 96ms of sustained speech):
  - Transition to LISTENING
  - Copy pre-roll buffer into speech buffer (captures audio before onset)
  - Emit `speech_started` event

### LISTENING State

- All audio chunks are accumulated in the speech buffer
- Each chunk is checked for silence
- Uses a **lower threshold** for end detection: `threshold × 0.6` (e.g., 0.3 if threshold is 0.5)
  - This asymmetry prevents premature cutoffs during brief pauses within speech
- Tracks cumulative silence duration in milliseconds
- When silence exceeds `silence_duration_ms` (default 600ms):
  - Extract all accumulated audio (PCM16 24kHz)
  - Transition back to IDLE
  - Reset VAD model state
  - Emit `speech_stopped` event with the audio data

## Configuration Parameters

| Parameter | Default | Description |
|-----------|---------|-------------|
| `threshold` | 0.5 | Speech probability threshold (0.0-1.0). Higher = less sensitive. |
| `silence_duration_ms` | 600 | Milliseconds of silence before declaring end of speech. |
| `prefix_padding_ms` | 300 | Pre-roll buffer duration. Audio before speech onset is included. |
| `start_chunks` | 3 | Consecutive chunks above threshold to trigger onset (96ms). |

### Tuning Guide

**For noisy environments:**
- Increase `threshold` to 0.6-0.7 to reduce false triggers
- Increase `start_chunks` to 4-5 for more confident onset detection

**For fast-paced conversation:**
- Decrease `silence_duration_ms` to 400-500 for quicker turn-taking
- Decrease `prefix_padding_ms` to 200 if the pre-roll captures too much noise

**For deliberate speakers with long pauses:**
- Increase `silence_duration_ms` to 800-1000 to avoid cutting off mid-thought

## Pre-roll Buffer

The pre-roll buffer captures audio from before the VAD detects speech onset. This is important because:

1. The VAD needs 3 consecutive chunks (96ms) to confirm speech
2. The actual speech may start 100-300ms before confident detection
3. Without pre-roll, the first syllable might be clipped

The buffer is a fixed-size ring buffer (deque):

```python
pre_roll_chunks = max(1, prefix_padding_ms // VAD_CHUNK_MS)
# With default 300ms / 32ms = 9 chunks ≈ 288ms of audio
self._pre_roll: deque[bytes] = deque(maxlen=pre_roll_chunks)
```

When speech is detected, the pre-roll contents are prepended to the speech buffer.

## Residual Buffer

Audio chunks from the client may not align perfectly with VAD chunk boundaries. After resampling from 24kHz to 16kHz, there may be leftover samples that don't fill a complete 512-sample VAD chunk.

The `_residual` buffer handles this:

```python
# Prepend leftover from previous call
data = self._residual + pcm16_24khz

# Process complete chunks
while i + chunk_size <= len(samples_16k):
    # ...process VAD chunk...

# Save leftover for next call
if leftover > 0:
    self._residual = data[used_bytes:]
```

This ensures no audio data is lost between calls, regardless of client chunk sizes.

## Events Emitted

### speech_started

```json
{
  "type": "input_audio_buffer.speech_started",
  "audio_start_ms": 1234,
  "event_id": "event_abc123..."
}
```

Emitted when VAD detects speech onset. `audio_start_ms` is the monotonic timestamp relative to session start.

### speech_stopped

```json
{
  "type": "input_audio_buffer.speech_stopped",
  "audio_end_ms": 5678,
  "event_id": "event_def456..."
}
```

Emitted when VAD detects speech end (after silence duration). In server_vad mode, this automatically triggers:
- `input_audio_buffer.committed` event
- The full STT → LLM → TTS pipeline

## Auto-commit on speech_stopped

In server_vad mode, when `speech_stopped` fires:

```python
async def _auto_commit(session, vad_audio):
    item_id = gen_item_id()
    await session.send(input_audio_buffer_committed(item_id))
    session.audio_buffer.clear()  # Use VAD audio, not the main buffer
    asyncio.create_task(_run_pipeline(session, vad_audio, item_id=item_id))
```

The pipeline uses the VAD-accumulated audio (which includes the pre-roll) rather than the session's raw audio buffer. This ensures only the detected speech segment is transcribed, not silence or noise before/after.

## AEC Mode Interaction

The VAD's behavior changes based on AEC mode when the assistant is speaking. See [aec.md](aec.md) and [non-aec.md](non-aec.md) for details.

Summary:
- **Non-AEC**: `process_chunk` returns empty list during playback (echo gate)
- **AEC**: VAD continues processing during playback, enabling barge-in detection
