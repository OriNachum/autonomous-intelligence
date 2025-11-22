# Add DOA Detection to Hearing App

## Goal
Add Direction of Arrival (DOA) detection to `record_respeaker.py` and `hearing_event_emitter.py` using the `ReachyMini` library (as demonstrated in `doa-example.py`). The DOA should be averaged over the recording/speech period.

## User Review Required
> [!IMPORTANT]
> This plan assumes `ReachyMini` can be used alongside `pyaudio` without resource conflicts. If `ReachyMini` locks the audio device, we may need to refactor how audio is accessed or use a different method for DOA.

## Proposed Changes

### Hearing App

#### [MODIFY] [record_respeaker.py](file:///home/thor/git/autonomous-intelligence/reachy-mini/hearing_app/record_respeaker.py)
- Import `ReachyMini` from `reachy_mini`.
- Initialize `ReachyMini` in `ReSpeakerRecorder` (or wrap the execution in `with ReachyMini(...)`).
- In the `record` method loop:
    - Call `mini.media.audio.get_DoA()` periodically.
    - Store valid DOA samples (where voice is detected).
- After recording:
    - Calculate the average DOA (handling the circular nature of angles if necessary, though simple average might be the starting point as requested).
    - Print the average DOA.
    - (Optional) Save DOA to a metadata file or just print it for now.

#### [MODIFY] [hearing_event_emitter.py](file:///home/thor/git/autonomous-intelligence/reachy-mini/hearing_app/hearing_event_emitter.py)
- Import `ReachyMini` from `reachy_mini`.
- Initialize `ReachyMini` in `HearingEventEmitter` (or wrap the run loop).
- In `HearingEventEmitter`:
    - Add a list to buffer DOA samples during speech.
    - In `handle_speech` (start of speech):
        - Clear DOA buffer.
    - In `process` or a separate task:
        - Periodically sample DOA using `mini.media.audio.get_DoA()` and update a `current_doa` state variable.
        - Maintain a buffer of DOA samples for averaging during speech segments.
    - Update `emit_event` to automatically include the `current_doa` (or a recently averaged value) in the event payload for ALL events (`speech_started`, `speech_partial`, `speech_stopped`).
    - For `speech_stopped`, specifically use the average DOA over the speech duration.

## Verification Plan

### Automated Tests
- None available for hardware interactions.

### Manual Verification
1. **Verify `record_respeaker.py`**:
    - Run `python3 hearing_app/record_respeaker.py --duration 5`.
    - Speak from a specific direction.
    - Check console output for "Average DOA: ...".
    - Verify the angle roughly matches the direction.

2. **Verify `hearing_event_emitter.py`**:
    - Run `python3 hearing_app/hearing_event_emitter.py --device reachy`.
    - Connect a client to the socket (or use `nc -U /tmp/reachy_sockets/hearing.sock`).
    - Speak to the robot.
    - Check the JSON output for `speech_stopped` event.
    - Verify it contains a `doa` field with a reasonable value.
