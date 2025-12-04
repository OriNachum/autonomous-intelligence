# Vision App Implementation Plan

## Goal
Create a standalone Dockerized application (`vision_app`) responsible for the entire video stack. It will capture video from `/dev/video0` using OpenCV, perform face recognition, manage a rolling buffer of frames, and emit events to the main `conversation_app`.

## Architecture

### 1. Docker Service (`vision_app`)
A new service will be added to `docker-compose.yml`.
- **Image**: Python 3.10-slim based.
- **Dependencies**: `opencv-python-headless`, `numpy`, `requests` (or `websockets`/`zmq`), `face_recognition` (optional, or use cv2's built-in).
- **Devices**: `/dev/video0` mapped to container.
- **Volumes**: 
  - Shared volume for video frames (e.g., `./data/frames:/app/frames`)
  - Shared volume for Unix domain events (/tmp/reachy_sockets:/tmp/reachy_sockets)
  - Device access (/dev:/dev)
- **Network**: `host` mode (for low latency and easy IPC).

### 2. Application Logic (`vision_app/main.py`)
The app will run a continuous loop:
1.  **Capture**: Read frames from `/dev/video0` using `cv2`.
2.  **Buffer**: Maintain a rolling buffer of the last X frames (configurable, e.g., 10 frames).
    *   Frames will be saved to the shared volume to be accessible by `conversation_app`.
    *   Old frames will be automatically deleted to save space.
3.  **Detection**:
    *   Use OpenCV (Haar Cascades or DNN module) for face detection.
    *   (Optional) Use `face_recognition` library for specific identity recognition if needed.
4.  **Event Emission**:
    *   When a relevant event occurs (e.g., "Face Detected", "Person Arrived"), emit an event.
    *   **Debouncing**: Ensure events aren't spammed (e.g., only emit "Face Detected" once every 5 seconds unless the face changes).
    *   **Payload**:
        ```json
        {
          "type": "visual_event",
          "data": {
            "label": "face_detected",
            "timestamp": 1234567890,
            "frames": [
              "/app/frames/frame_t-9.jpg",
              ...
              "/app/frames/frame_t.jpg"
            ],
            "metadata": {
              "count": 1,
              "position": {"x": 100, "y": 100, "w": 50, "h": 50}
            }
          }
        }
        ```

### 3. Communication Mechanism
To enable `vision_app` to send events to `conversation_app`:

*   **Modification to `conversation_app/gateway.py`**:
    *   Update `ReachyGateway` to listen for incoming messages on its Unix socket (or a new dedicated socket/port).
    *   Currently, `gateway.py` only *broadcasts* events. We will add a reader task that listens for JSON messages from connected clients and injects them into the event loop, triggering `on_gateway_event` in `app.py`.

### 4. Integration with `app.py`
*   `app.py` will receive the `visual_event`.
*   It will parse the event, and if it's significant (e.g., a new face), it can trigger a conversation interrupt or context update.
*   The frame paths provided in the event will be accessible since both apps share the `./data/frames` volume.

## Implementation Steps

### Step 1: Create Vision App Structure
*   Create directory `vision_app/`.
*   Create `vision_app/Dockerfile`.
*   Create `vision_app/requirements.txt`.
*   Create `vision_app/main.py`.

### Step 2: Update `docker-compose.yml`
*   Add `vision_service` definition.
*   Configure volumes and devices.

### Step 3: Modify `conversation_app/gateway.py`
*   Implement `handle_client_messages` in `ReachyGateway`.
*   Ensure incoming socket messages are dispatched to `self.event_callback`.

### Step 4: Develop Vision Logic
*   Implement the OpenCV capture loop.
*   Implement the rolling buffer (saving/deleting files).
*   Implement face detection.
*   Implement the socket client to send events to `gateway.py`.

### Step 5: Verify
*   Run `docker-compose up`.
*   Verify `vision_app` is running and capturing frames.
*   Verify `conversation_app` receives "face_detected" events.
*   Verify `app.py` logs the event and frames.

## Definition of Done
*   [ ] `vision_app` Dockerfile and code created.
*   [ ] `docker-compose.yml` updated.
*   [ ] `gateway.py` updated to receive events.
*   [ ] System successfully detects a face and logs the event in `conversation_app`.
