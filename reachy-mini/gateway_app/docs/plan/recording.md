# Refactor Recording to use ReachyMini

## Goal Description
Refactor `gateway_app/gateway.py` to use `ReachyMini`'s built-in recording capabilities (via `DoADetector`) instead of managing `pyaudio` directly. This aligns the recording implementation with the existing VAD/DOA implementation which already uses `ReachyMini`.

## User Review Required
> [!IMPORTANT]
> This change removes direct `pyaudio` control from `gateway.py`. Ensure `ReachyMini` is correctly configured to use the desired audio backend (default/gstreamer) if specific configuration was relied upon.
> The `ReachyMini` instance is managed by `DoADetector`.

## Proposed Changes

### Gateway App

#### [MODIFY] [doa_detector.py](file:///home/thor/git/autonomous-intelligence/reachy-mini/gateway_app/doa_detector.py)
- Expose recording methods from the internal `ReachyMini` instance:
    - `start_recording()`
    - `stop_recording()`
    - `get_audio_sample()`
    - `get_sample_rate()`

#### [MODIFY] [gateway.py](file:///home/thor/git/autonomous-intelligence/reachy-mini/gateway_app/gateway.py)
- Remove `pyaudio` imports and initialization.
- Remove `initialize_input_device`, `find_input_device`, and `setup_audio_stream` methods.
- Update `run()` to start recording via `self.doa_detector.start_recording()`.
- Update `listen()` to fetch samples via `self.doa_detector.get_audio_sample()`.
    - Handle potential data type conversion (float to int16) if `ReachyMini` returns float arrays.
- Update `cleanup()` to stop recording via `self.doa_detector.stop_recording()`.

## Verification Plan

### Automated Tests
- None available for hardware-specific audio recording.

### Manual Verification
- **Deploy and Run**:
    1. Run `python3 gateway_app/gateway.py`.
    2. Verify "Reachy Gateway starting..." log.
    3. Verify "DOA detector initialized" log.
    4. Speak into the microphone.
    5. Verify "Speech detected" and "Speech stopped" events in logs.
    6. Verify transcription is successful (implies audio data is correctly captured and formatted).
