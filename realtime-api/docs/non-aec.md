# Non-AEC Mode (Echo Gate)

Non-AEC mode is the default operating mode for devices without hardware acoustic echo cancellation. It uses a simple **echo gate** strategy: all microphone input is silenced while the assistant is speaking, preventing feedback loops.

## How It Works

When `aec_mode: "none"` (the default):

```
Assistant NOT speaking:
  └── VAD processes audio normally
      └── Detects speech → triggers STT → LLM → TTS pipeline

Assistant IS speaking (is_speaking = True):
  └── ALL audio input is discarded
      └── No VAD processing
      └── No barge-in possible
      └── User must wait for response to finish
```

The echo gate is implemented at the VAD level — the very first check in `process_chunk`:

```python
def process_chunk(self, pcm16_24khz: bytes) -> list[VADEvent]:
    if self.is_speaking and self.aec_mode == AECMode.NONE:
        return []  # Discard everything
```

## Why Echo Gating?

Without hardware AEC, a standard microphone picks up everything:
- The assistant's speech from the speaker
- Room reflections and reverberations
- The user's actual speech (if any)

There is no reliable way to separate the user's voice from the playback echo in software alone. The VAD would constantly trigger on the assistant's own audio, creating a feedback loop where the system interrupts itself.

The echo gate is a simple, reliable solution: if we're playing audio, don't listen.

## Enabling Non-AEC Mode

Non-AEC is the default. You can explicitly set it:

### Via Session Update

```json
{
  "type": "session.update",
  "session": {
    "turn_detection": {
      "type": "server_vad",
      "aec_mode": "none"
    }
  }
}
```

### Via Environment Variable

```bash
DEFAULT_AEC_MODE=none
```

## Conversation Flow

```
1. User speaks → VAD detects → speech_started event
2. User pauses → VAD detects → speech_stopped event → auto-commit
3. STT transcribes → LLM generates → TTS streams
4. During TTS playback:
   ├── is_speaking = True
   ├── All audio input silenced
   └── User cannot interrupt
5. TTS finishes → is_speaking = False
6. VAD resets → echo cooldown
7. Back to step 1
```

## Post-Response Cleanup

After the assistant finishes speaking, the system performs cleanup to prevent false triggers from residual echo:

```python
# In _generate_response, after response completes:
session.is_speaking = False

# Reset VAD if non-AEC mode
if session.vad and not _is_aec_mode(session):
    session.vad.reset()
```

The VAD reset clears:
- Internal model states (Silero VAD recurrent state)
- Pre-roll buffer
- Speech accumulation buffer
- Start count and silence timers

This prevents any lingering echo energy from triggering a false speech detection.

## Limitations

1. **No interruption** — The user must wait for the full response before speaking
2. **Turn-taking delay** — There's a brief gap after the response ends before the system starts listening again
3. **Long responses** — If the assistant generates a lengthy response, the user has no way to cut it short (except via manual `response.cancel` event)

## When to Use

**Use non-AEC mode when:**
- Using a standard laptop, desktop, or phone microphone
- The speaker and microphone are in close proximity
- You don't have XMOS ReSpeaker or similar AEC hardware
- You prefer simple, predictable turn-taking behavior

**Consider AEC mode instead when:**
- You have hardware AEC (XMOS XVF-3000, XVF-3800)
- Natural conversation with interruption support is important
- The use case involves quick back-and-forth dialogue

## Manual Interruption Alternative

Even in non-AEC mode, clients can programmatically cancel a response:

```json
{
  "type": "response.cancel"
}
```

This sets `session.cancel_event`, which stops LLM streaming and TTS synthesis. The response is finalized with `status: "cancelled"`. A client UI could provide a "stop" button that sends this event.

## Comparison with AEC Mode

| Behavior | Non-AEC (echo gate) | AEC |
|----------|---------------------|-----|
| Audio during playback | Discarded | Processed |
| Barge-in | Not possible | Intelligent (LLM decision) |
| Echo feedback risk | None | None (hardware handles it) |
| Hardware requirement | Any microphone | AEC microphone required |
| Post-response reset | VAD state cleared | VAD continues |
| User experience | Turn-based | Conversational |
| Complexity | Simple | Requires STT + LLM for decision |
