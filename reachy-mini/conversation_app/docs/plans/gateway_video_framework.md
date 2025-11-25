# Gateway Video Framework Plan

## Goal
Create a new `GatewayVideo` component to handle video processing from Reachy's camera.
Initially, it will capture frames from the WebRTC stream, and every 100th frame:
1.  Save the frame to disk.
2.  Emit an event with the frame path.

## Architecture

### `GatewayVideo` Class
Located in `conversation_app/gateway_video.py`.

#### Responsibilities:
1.  **Connect to WebRTC Stream**: Use `Gst` and `webrtcsrc` to consume video from Reachy.
2.  **Frame Extraction**: Use `appsink` to capture raw video frames.
3.  **Frame Processing**:
    *   Count frames.
    *   Every Nth (100) frame:
        *   Convert GStreamer buffer to image (numpy array/PIL).
        *   Save image to `videos/` directory.
        *   Emit `video_frame_captured` event.
4.  **Lifecycle Management**: `start()`, `stop()`, `cleanup()`.

#### Integration with `gateway.py`:
*   Initialize `GatewayVideo` in `ReachyGateway`.
*   Pass `event_callback` to `GatewayVideo`.
*   Manage `GatewayVideo` lifecycle alongside `GatewayAudio`.

## Implementation Details

### 1. Dependencies
*   `gi` (GObject Introspection)
*   `gstreamer` (Gst, GstWebRTC, GstSdp)
*   `opencv-python` (cv2) or `PIL` (Pillow) and `numpy` for image saving.
    *   We will use `cv2` if available, otherwise `PIL`.

### 2. GStreamer Pipeline
*   Source: `webrtcsrc`
*   Video Sink: `appsink` with `emit-signals=True`, `sync=False`, `caps="video/x-raw, format=RGB"` (or BGR).

### 3. Event Loop Integration
*   GStreamer requires a GLib `MainLoop` or manual iteration of the bus.
*   Since `gateway.py` uses `asyncio`, we need to run the GStreamer loop in a separate thread or integrate it.
*   `reachy_camera_example.py` uses a while loop with `bus.timed_pop_filtered`. We can run this loop in a separate thread or `asyncio.to_thread`.

### 4. File Structure
*   `conversation_app/gateway_video.py`: New file.
*   `conversation_app/gateway.py`: Update to include `GatewayVideo`.

## Step-by-Step Plan

1.  **Create `conversation_app/gateway_video.py`**:
    *   Implement `GatewayVideo` class.
    *   Implement `GstConsumer` logic adapted for `appsink`.
    *   Implement `_on_new_sample` callback for `appsink`.
    *   Implement frame saving and event emission.

2.  **Update `conversation_app/gateway.py`**:
    *   Import `GatewayVideo`.
    *   Initialize `GatewayVideo` in `__init__`.
    *   Start `GatewayVideo` in `run`.
    *   Ensure cleanup in `cleanup`.

3.  **Verification**:
    *   Run `gateway.py`.
    *   Verify images are saved to `videos/`.
    *   Verify events are emitted (check logs or socket output).
