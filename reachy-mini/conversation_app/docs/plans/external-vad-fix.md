# Fix VAD Detector Error

## Goal Description
The `vad_detector.py` module throws "Error while processing frame" because `webrtcvad` receives audio chunks of incorrect size. `webrtcvad` strictly requires 10, 20, or 30ms chunks (e.g., 480 samples at 16kHz for 30ms). The current `GatewayAudio.listen` method directly passes whatever chunk size `reachy_controller.get_audio_sample()` returns, which varies or is incorrect.

This plan implements a buffering mechanism in `GatewayAudio` to ensure `vad_detector` always receives chunks of the exact required size.

## User Review Required
> [!NOTE]
> This change modifies how audio is buffered and processed. It ensures stability but might introduce a tiny latency (max 30ms) due to buffering.

## Proposed Changes

### conversation_app

#### [MODIFY] [gateway_audio.py](file:///home/thor/git/autonomous-intelligence/reachy-mini/conversation_app/gateway_audio.py)
- Update `listen` method:
    - Introduce `self.incoming_buffer` (numpy array) to accumulate raw samples.
    - Append new samples from `reachy_controller` to `self.incoming_buffer`.
    - Loop while `len(self.incoming_buffer) >= self.chunk_size`:
        - Extract exact `self.chunk_size` slice.
        - Process this slice (add to `audio_buffer` for VAD, handle recording/pre-roll).
        - Remove slice from `self.incoming_buffer`.

#### [MODIFY] [vad_detector.py](file:///home/thor/git/autonomous-intelligence/reachy-mini/conversation_app/vad_detector.py)
- Update `is_speech` method:
    - Improve error logging to include the length of `audio_data` when an exception occurs. This aids in verifying the fix and debugging future issues.

## Verification Plan

### Automated Tests
- Create a reproduction script `tests/test_vad_buffering.py` (or similar) that:
    1. Mocks `ReachyController` to return random-sized audio chunks (e.g., 100 samples, 500 samples).
    2. Instantiates `GatewayAudio` with a mock event callback.
    3. Feeds these chunks to `GatewayAudio`.
    4. Verifies that `vad_detector.is_speech` is called with exactly 480 bytes (or whatever the configured chunk size is).
    5. Verifies no "Error while processing frame" logs are generated.

### Manual Verification
- Deploy to robot (User action).
- Check logs for "Error in VAD processing".
- Verify VAD functionality (speech detection) works as expected.
