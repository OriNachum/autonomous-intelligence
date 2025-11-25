# Video Gateway Framework Implementation Plan

## Goal Description
Implement a new `GatewayVideo` component to handle video processing for the Reachy robot. Initially, this will be a "dummy" implementation that captures video frames, saves every 100th frame to disk, and emits an event with the file path (URL). This serves as a framework for future computer vision tasks.

## User Review Required
> [!IMPORTANT]
> I am assuming standard OpenCV (`cv2`) usage for video capture as no specific video interface was found in `ReachyMini` usage examples.

## Proposed Changes

### Conversation App

#### [NEW] [gateway_video.py](file:///home/thor/git/autonomous-intelligence/reachy-mini/conversation_app/gateway_video.py)
- Create `GatewayVideo` class.
- Initialize `cv2.VideoCapture`.
- Implement `process()` loop:
    - Capture frames continuously.
    - Every 100th frame:
        - Save frame to `videos/` directory (ensure directory exists).
        - Emit `video_frame` event with `file_path` and `timestamp`.
- Implement `cleanup()` to release camera.

#### [MODIFY] [gateway.py](file:///home/thor/git/autonomous-intelligence/reachy-mini/conversation_app/gateway.py)
- Import `GatewayVideo`.
- Initialize `GatewayVideo` in `ReachyGateway.__init__`.
- Start `gateway_video.process()` task in `run()`.
- Call `gateway_video.cleanup()` in `cleanup()`.

#### [MODIFY] [requirements.txt](file:///home/thor/git/autonomous-intelligence/reachy-mini/requirements.txt)
- Add `opencv-python` to dependencies.

#### [MODIFY] [app.py](file:///home/thor/git/autonomous-intelligence/reachy-mini/conversation_app/app.py)
- Add handling for `video_frame` event in `on_gateway_event`.
- Store the latest frame URL in memory (e.g., `self.latest_frame_path`).
- Log the reception of the frame.

## Verification Plan

### Automated Tests
- None for this initial implementation as it involves hardware (camera).

### Manual Verification
1.  **Run the Gateway**:
    - Start the application: `python3 -m conversation_app.app`
2.  **Verify Video Capture**:
    - Check if the `videos/` directory is created.
    - Verify that images are being saved to `videos/` approximately every few seconds (depending on framerate).
3.  **Verify Event Emission**:
    - Check the logs for "Emitted event: video_frame".
    - Check the logs in `app.py` for "Received video frame: ..."
