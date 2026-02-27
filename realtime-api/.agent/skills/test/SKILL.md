---
name: test
description: Run TTS round-trip tests — pure-logic unit tests and optional integration tests against live TTS/STT services.
triggers:
  - test
  - run tests
  - test tts
  - verify
  - check
---

# Test Realtime-API

Run unit tests and integration tests for the TTS pipeline.

## When to use

- After deploying new code
- When the user says "test", "run tests", "verify", "check"
- To validate TTS chunking and sentence splitting logic

## Instructions

### Quick — pure-logic tests only (no network, instant):

```bash
cd /home/spark/git/autonomous-intelligence/realtime-api && bash scripts/test_tts.sh --logic-only
```

### Full — includes TTS/STT round-trip (requires running containers):

```bash
cd /home/spark/git/autonomous-intelligence/realtime-api && bash scripts/test_tts.sh
```

## What the tests cover

### Pure-logic tests (always run)
- **Dash splitting**: em-dash-heavy text > 200 chars splits correctly in loose mode
- **TTS chunking**: 1000+ char comma-heavy text splits into chunks <= 800 chars
- **Short text passthrough**: text under 800 chars is not split

### Integration tests (require TTS + STT containers)
- **Whole-mode TTS**: full text → TTS → resample → STT round-trip
- **Sentence-mode TTS**: split → per-sentence TTS → concatenate → STT round-trip
- **Duration comparison**: whole vs sentence mode within tolerance

## After testing

Speak the result:

```bash
/home/spark/git/autonomous-intelligence/realtime-api/scripts/speak.sh "All tests passed."
```
