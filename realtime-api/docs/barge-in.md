# Intelligent Barge-in

Barge-in is the ability for a user to interrupt the assistant while it's speaking. The Realtime API implements an **LLM-based intelligent barge-in** system that distinguishes real interruptions from casual backchannels like "yeah", "mmhmm", or "ok".

This feature is only active in **AEC mode** (acoustic echo cancellation devices). In non-AEC mode, all audio input is silenced during playback (echo gate).

## The Problem

When a user speaks during assistant playback, there are two possibilities:

1. **Backchannel** — The user is acknowledging what was said ("yeah", "uh-huh", "right", "ok", "interesting"). The assistant should keep talking.
2. **Interruption** — The user wants to take over ("wait", "actually", "no", "stop", a new question, a correction). The assistant should stop and listen.

Naively cancelling on any detected speech creates a poor experience — the assistant stops every time the user makes a noise.

## How It Works

```
User speaks during assistant playback
    │
    ▼
VAD detects speech_started (is_speaking=True, AEC mode)
    │
    ▼
VAD accumulates audio until speech_stopped
    │
    ▼
BargeInEvaluator.evaluate()
    │
    ├── 1. Quick-transcribe via Parakeet STT (1-3 words)
    │
    ├── 2. Build minimal LLM prompt:
    │       System: "Decide STOP or CONTINUE"
    │       User: assistant's last ~200 chars + user's transcript
    │
    ├── 3. Fast LLM call (max_tokens=1, temperature=0)
    │
    ├── STOP → Cancel response, start new turn with captured audio
    │
    └── CONTINUE → Discard snippet, keep playing
```

## LLM Decision Prompt

The system prompt sent to the LLM:

```
You are a conversation flow controller. The assistant is currently speaking.
The user just said something. Decide: should the assistant STOP speaking and listen,
or CONTINUE speaking (the user is just acknowledging/backchanneling)?
Reply with exactly one word: STOP or CONTINUE.
```

The user message contains two pieces of context:

```
Assistant's last words: "...{last 200 characters of current response}..."
User said: "{transcribed 1-3 words}"
```

## Latency Budget

The barge-in evaluation runs while TTS playback continues uninterrupted:

| Phase | Time |
|-------|------|
| VAD speech accumulation | Variable (until silence detected) |
| Parakeet STT transcription | ~100-200ms (short audio is fast) |
| LLM decision | ~100-200ms (1 token, minimal prompt) |
| **Total overhead** | **~200-400ms after speech ends** |

During this entire evaluation, the assistant's audio keeps streaming to the client. The user perceives no delay — either the response continues naturally, or it stops shortly after they finish speaking.

## Configuration

```python
# config.py Settings
barge_in_window_ms: int = 750     # Not currently used for windowing (VAD handles accumulation)
barge_in_model: str | None = None  # Optional faster model for decision LLM call
```

Environment variables:
```
BARGE_IN_MODEL=        # Use a smaller/faster model for decisions (e.g., a local 1B model)
```

If `barge_in_model` is not set, the main `OPENAI_MODEL` is used.

## Decision Examples

**CONTINUE (backchannels):**
- "yeah" — User is agreeing
- "mmhmm" — Listening signal
- "ok" — Acknowledgment
- "right" — Agreement
- "uh huh" — Active listening
- "go on" — Encouraging continuation
- "interesting" — Showing engagement

**STOP (interruptions):**
- "wait" — Wants to pause
- "actually" — Correction incoming
- "no" — Disagreement
- "stop" — Explicit stop
- "but" — Counter-argument
- "what about" — New question
- Any clear question — Topic shift

## Edge Cases

### Empty Transcription
If Parakeet returns an empty transcript (noise, unclear audio), the evaluator defaults to **CONTINUE** — don't interrupt for unintelligible sounds.

### LLM Error
If the LLM call fails (timeout, connection error), the evaluator defaults to **STOP** — better to pause and let the user re-engage than to talk over them.

### Rapid Successive Barge-ins
Each barge-in evaluation is independent. If the user makes multiple sounds during a response, each triggers a separate evaluation after the VAD detects a speech_stopped event.

## Flow in ws_handler.py

```python
# In _handle_audio_append, when VAD fires speech_stopped during is_speaking + AEC:
async def _evaluate_barge_in(session, audio_bytes):
    evaluator = BargeInEvaluator()
    decision = await evaluator.evaluate(
        audio_pcm16_24khz=audio_bytes,
        assistant_last_text=session.current_response_text,
    )
    if decision == "STOP":
        await _handle_response_cancel(session)     # Cancel current TTS/LLM
        await _run_pipeline(session, audio_bytes)   # Start new turn with captured audio
    # If CONTINUE: do nothing, playback continues
```

When the decision is STOP:
1. `session.cancel_event` is set, stopping LLM streaming and TTS synthesis
2. The response is finalized with `status: "cancelled"`
3. A new pipeline starts immediately using the barge-in audio as input — no need for the user to repeat themselves

## Compared to Simple Barge-in

| Feature | Simple Barge-in | Intelligent Barge-in |
|---------|-----------------|---------------------|
| Detection | Any speech → cancel | Speech → evaluate → decide |
| False positives | High (backchannels cancel) | Low (backchannels ignored) |
| Latency | Instant | ~200-400ms after speech |
| Requires LLM | No | Yes (1-token call) |
| User experience | Frustrating with backchannels | Natural conversation flow |
