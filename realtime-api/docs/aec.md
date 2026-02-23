# AEC Mode (Acoustic Echo Cancellation)

AEC mode is designed for hardware devices that have built-in acoustic echo cancellation, such as the XMOS ReSpeaker family. It enables true bidirectional conversation where the user can speak while the assistant is responding.

## What is AEC?

Acoustic Echo Cancellation (AEC) is hardware-level signal processing that removes the assistant's own voice from the microphone input. Without AEC, when the assistant speaks through a speaker, the microphone picks up that audio and creates a feedback loop — the system "hears itself" and may interpret its own speech as user input.

**AEC devices** solve this by processing the raw microphone signal to subtract the known playback audio, producing a clean signal containing only the user's voice.

## Supported Devices

The system was designed for XMOS-based ReSpeaker devices:

| Device | Channels | USB ID | AEC Channel |
|--------|----------|--------|-------------|
| XVF-3000 (ReSpeaker 4 Mic Array v2.0) | 6-ch capture | 2886:0018 | Channel 0 |
| XVF-3800 (ReSpeaker XVF3800) | 2-ch capture | 2886:0037 | Channel 0 |

Both devices output AEC-processed audio on channel 0, which is what the system captures and sends to VAD.

## Enabling AEC Mode

### Via Session Update

```json
{
  "type": "session.update",
  "session": {
    "turn_detection": {
      "type": "server_vad",
      "threshold": 0.5,
      "silence_duration_ms": 600,
      "prefix_padding_ms": 300,
      "aec_mode": "aec"
    }
  }
}
```

### Via Environment Variable

```bash
DEFAULT_AEC_MODE=aec
```

## Behavior During Response Playback

When the assistant is speaking (`is_speaking = True`) and AEC mode is active:

1. **VAD continues processing** — Audio input is NOT silenced
2. The VAD state machine keeps running, looking for speech onset
3. If speech is detected → **intelligent barge-in evaluation** kicks in
4. The barge-in system decides whether to STOP or CONTINUE (see [barge-in.md](barge-in.md))

This is in contrast to non-AEC mode, where all audio input is discarded during playback.

## Audio Flow in AEC Mode

```
Client sends audio continuously
    │
    ▼
VAD processes every chunk (even during playback)
    │
    ├── No speech detected → continue normally
    │
    └── Speech detected during assistant playback
        │
        ▼
    VAD accumulates speech until silence
        │
        ▼
    BargeInEvaluator runs:
        ├── Transcribe snippet (STT)
        ├── LLM decides: STOP or CONTINUE
        │
        ├── STOP: Cancel response → new turn
        └── CONTINUE: Discard → keep playing
```

## Why AEC Requires Hardware Support

Software echo cancellation exists but is unreliable in real-time voice systems:
- It requires precise timing alignment between playback and capture
- Room acoustics vary (reverb, reflections)
- Non-linear distortions from speakers are hard to model

Hardware AEC (like XMOS XVF-3000/3800) uses dedicated DSP with access to both the speaker output signal and multi-microphone array input, achieving echo cancellation that is reliable enough for real-time conversation.

## When to Use AEC Mode

**Use AEC mode when:**
- The client device has a hardware AEC microphone (XMOS ReSpeaker, etc.)
- You want natural conversation with interruption support
- The user might need to correct, redirect, or stop the assistant mid-response

**Do NOT use AEC mode when:**
- Using a regular laptop/desktop microphone (no hardware AEC)
- The playback device is close to the microphone
- You're in a text-only or push-to-talk workflow

Using AEC mode without actual hardware AEC will cause the system to detect its own speech as user input, triggering constant barge-in evaluations.

## Implementation Details

### VAD State (`vad.py`)

```python
class ServerVAD:
    aec_mode: AECMode = AECMode.NONE
    is_speaking: bool = False

    def process_chunk(self, pcm16_24khz: bytes) -> list[VADEvent]:
        # Echo gate: if speaking and non-AEC, discard
        if self.is_speaking and self.aec_mode == AECMode.NONE:
            return []
        # Otherwise, process normally (AEC mode or not speaking)
        ...
```

### WebSocket Handler (`ws_handler.py`)

The `is_speaking` flag on the VAD is synchronized with the session state:

```python
async def _handle_audio_append(session, data):
    vad.is_speaking = session.is_speaking  # Sync before processing
    vad_events = vad.process_chunk(pcm_bytes)
    for event in vad_events:
        if event.type == SPEECH_STOPPED and session.is_speaking and is_aec_mode:
            # Trigger barge-in evaluation
            asyncio.create_task(_evaluate_barge_in(session, event.audio_bytes))
```

### Session Config

The `aec_mode` field is part of `TurnDetectionConfig`:

```python
@dataclass
class TurnDetectionConfig:
    type: str = "server_vad"
    threshold: float = 0.5
    silence_duration_ms: int = 600
    prefix_padding_ms: int = 300
    aec_mode: str = "none"  # "none" or "aec"
```

It can be changed at any time via `session.update` — the VAD is re-initialized when the config changes.
