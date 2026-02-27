---
name: speak
description: Speak text aloud using the Magpie TTS container in the realtime-api Docker stack. Zero external dependencies — just curl + aplay.
triggers:
  - speak
  - say
  - tell me
  - read aloud
  - announce
---

# Speak via Magpie TTS

Synthesize speech using the local Magpie TTS container (port 9000) and play through speakers.

## When to use

- When the user says "speak", "say", "tell me", "read aloud"
- After completing a significant task — speak a brief 1-2 sentence summary
- When the user asks you to announce or vocalize something
- To give audio feedback on deploy/test results

## Usage

```bash
/home/spark/git/autonomous-intelligence/realtime-api/scripts/speak.sh "Text to speak"
```

## Options

| Flag | Short | Default | Description |
|------|-------|---------|-------------|
| (positional) | | (required) | Text to speak |
| `--voice` | `-v` | `Mia.Calm` | Voice name |
| `--speed` | `-s` | `125` | Speed percentage |
| `--url` | `-u` | `http://localhost:9000` | Magpie TTS URL |

## Voices

Mia, Mia.Calm, Mia.Happy, Mia.Sad, Mia.Angry, Aria, Aria.Calm, Aria.Happy, Jason, Jason.Calm, Leo, Leo.Calm

## Examples

```bash
# Default calm voice
/home/spark/git/autonomous-intelligence/realtime-api/scripts/speak.sh "Deploy complete. All seven checks passed."

# Happy announcement
/home/spark/git/autonomous-intelligence/realtime-api/scripts/speak.sh -v Mia.Happy "All tests passed!"

# Different speed
/home/spark/git/autonomous-intelligence/realtime-api/scripts/speak.sh -s 140 "Speaking faster now."
```

## Notes

- Uses the Magpie TTS container from the realtime-api docker-compose stack (localhost:9000)
- No Python dependencies — just curl and aplay
- Audio plays through PipeWire/ALSA
- Keep messages concise (1-2 sentences) for task summaries
