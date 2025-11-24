# Fix Hearing/Recording Implementation Plan

## Goal
Fix the broken recording functionality in `gateway_app` where the robot cannot understand speech. The issue is caused by `ReachyMini` returning stereo audio (2 channels) which is not correctly processed into mono (channel 0) before being sent to VAD and Whisper, unlike the working `hearing_app` implementation.

## User Review Required
> [!IMPORTANT]
> This change will modify `gateway_app/reachy_controller.py` to strictly return mono audio (Channel 0) from `get_audio_sample()`. This assumes Channel 0 is always the AEC-processed channel we want, which matches the logic in `hearing_app`.

## Proposed Changes

### Gateway App

#### [MODIFY] [reachy_controller.py](file:///home/thor/git/autonomous-intelligence/reachy-mini/gateway_app/reachy_controller.py)
- Update `get_audio_sample()` to:
    - Check if the returned sample has 2 channels (shape `(N, 2)`).
    - If so, select only Channel 0 (AEC channel).
    - Ensure the returned array is 1D (mono).
    - Log the shape transformation for debugging.

#### [MODIFY] [gateway.py](file:///home/thor/git/autonomous-intelligence/reachy-mini/gateway_app/gateway.py)
- Verify `process()` and `listen()` loops handle the mono input correctly.
- (Optional) Add extra logging to confirm the data shape being passed to VAD/Whisper.

## Verification Plan

### Automated Tests
- None available for this specific hardware interaction.

### Manual Verification
1.  **Rebuild and Restart**:
    - `docker compose -f docker-compose-vllm.yml up -d --build reachy-gateway`
2.  **Check Logs**:
    - `docker compose -f docker-compose-vllm.yml logs -f reachy-gateway`
    - Verify logs show "Got audio sample with shape: (N,)" (mono) instead of "(N, 2)".
    - Verify VAD/DOA speech detection is working (logs showing "Speech detected").
    - Verify Transcription is working (logs showing "Transcription result: '...'").
3.  **Functional Test**:
    - Speak to the robot.
    - Confirm it detects speech and transcribes it correctly.
