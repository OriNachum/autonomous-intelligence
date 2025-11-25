# Audio Component Extraction Plan

## Goal
Extract the audio processing logic from `conversation_app/gateway.py` into a new module `conversation_app/gateway_audio.py` to prepare for other streams of inputs. The `use_vad` toggle and `Reachy` class usage will be preserved.

## User Review Required
> [!IMPORTANT]
> This refactoring moves significant logic. While behavior should remain identical, the internal structure will change.

## Proposed Changes

### [conversation_app]

#### [NEW] [gateway_audio.py](file:///home/thor/git/autonomous-intelligence/reachy-mini/conversation_app/gateway_audio.py)
- Create `GatewayAudio` class.
- Move audio configuration (sample rate, thresholds, etc.) from `ReachyGateway`.
- Move audio buffers and state variables.
- Move `WhisperSTT` initialization.
- Move `VADDetector` initialization.
- Implement methods extracted from `ReachyGateway`:
    - `listen()`: Audio capture loop.
    - `process()`: Audio processing loop.
    - `handle_speech()`, `handle_silence()`, `process_speech()`, `process_partial_speech()`.
    - `transcribe_audio()`.
    - `save_audio_file()`, `save_recording()`.
    - `sample_doa()`: DOA sampling loop.
    - `is_speech()`: VAD/DOA check.
- `GatewayAudio` will accept `reachy_controller` and an `event_callback` in `__init__`.

#### [MODIFY] [gateway.py](file:///home/thor/git/autonomous-intelligence/reachy-mini/conversation_app/gateway.py)
- Import `GatewayAudio`.
- Remove audio-related configuration, buffers, and state from `ReachyGateway.__init__`.
- Remove audio-related methods (`listen`, `process`, `handle_speech`, etc.).
- Instantiate `GatewayAudio` in `__init__`, passing `self.reachy_controller` and `self.emit_event` (or a wrapper).
- Update `run()` to start tasks from `self.gateway_audio` (`listen`, `process`, `sample_doa`).
- Update `cleanup()` to call `self.gateway_audio.cleanup()` (if needed, or just stop tasks).

## Verification Plan

### Automated Tests
- Run existing tests to ensure no regression.
    - `pytest conversation_app/tests/` (if any relevant tests exist).
    - `python3 conversation_app/verify_logging.py` (checks logging, might implicitly check audio flow if it simulates it).

### Manual Verification
- Run the gateway and verify it still records and processes audio.
    - Command: `python3 conversation_app/gateway.py --device Reachy` (or default).
    - Speak to the robot and verify:
        - "Speech started" and "Speech stopped" logs appear.
        - Transcription is output.
        - Audio files are saved (if enabled).
        - DOA events are emitted.
