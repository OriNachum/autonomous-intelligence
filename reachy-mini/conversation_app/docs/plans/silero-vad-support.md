# Silero VAD Support Plan

## Goal Description
Replace the existing WebRTC VAD with Silero VAD to improve speech detection accuracy and reduce false positives, specifically triggered by keyboard typing sounds. Silero VAD is generally more robust to noise and non-speech sounds.

## User Review Required
> [!IMPORTANT]
> This change introduces a dependency on `torch` (which seems to be already used in `gateway_audio.py` but not explicitly in `requirements.txt` for VAD purposes).
> The Silero VAD model will be downloaded from torch hub on the first run.

## Proposed Changes

### conversation_app

#### [MODIFY] [vad_detector.py](file:///home/thor/git/autonomous-intelligence/reachy-mini/conversation_app/vad_detector.py)
- Refactor `VADDetector` to support multiple backends or create a new `SileroVAD` class.
- Implement Silero VAD using `torch.hub.load`.
- Add a method to process audio chunks compatible with Silero (it accepts flexible chunk sizes, unlike WebRTC).
- Ensure the `is_speech` interface remains consistent or is adapted to handle the differences (Silero returns a probability, we'll need a threshold).

#### [MODIFY] [gateway_audio.py](file:///home/thor/git/autonomous-intelligence/reachy-mini/conversation_app/gateway_audio.py)
- Update initialization to allow selecting VAD type (WebRTC vs Silero) via environment variable (e.g., `VAD_TYPE=silero`).
- Adjust chunk size if necessary. Silero works well with larger chunks (e.g., 512 samples / 32ms at 16kHz) or can handle streams.
- If using Silero, we might want to use its stateful model to handle context better.

#### [MODIFY] [requirements.txt](file:///home/thor/git/autonomous-intelligence/reachy-mini/conversation_app/requirements.txt)
- Ensure `torch` is listed if it's not already (it is used in `gateway_audio.py` but not in requirements).
- Add `torchaudio` if needed by Silero loader.

## Verification Plan

### Automated Tests
- Create a unit test `tests/test_silero_vad.py` that:
    - Mocks `torch.hub.load` to avoid network calls during testing (or allows it if acceptable).
    - Feeds silence and speech samples to the detector.
    - Verifies it returns expected booleans.

### Manual Verification
1.  **Setup**: Set `VAD_TYPE=silero` in environment.
2.  **Run**: Start the gateway.
3.  **Test**:
    - Speak into the microphone -> Verify "Speech detected" logs.
    - Type on the keyboard -> Verify NO "Speech detected" logs (or significantly fewer than WebRTC).
    - Remain silent -> Verify NO "Speech detected" logs.
