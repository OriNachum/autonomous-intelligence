# Plan: Toggle Vision/Video

## Goal
Make vision and video processing optional in `conversation_app`. The application should be able to run without `opencv-python` and `PyGObject` installed. Vision functionality will be controlled via an environment variable `ENABLE_VISION`.

## User Review Required
> [!IMPORTANT]
> **Environment Variable**: A new environment variable `ENABLE_VISION` (default: `false`) will control whether video processing is enabled.
> **Dependencies**: The application will no longer crash if `gi` (PyGObject) or `cv2` (OpenCV) are missing, provided `ENABLE_VISION` is false.

## Proposed Changes

### `conversation_app/gateway_video.py`
- Wrap top-level `gi` (GStreamer) imports in `try...except ImportError`.
- Define a flag `HAS_GST` to indicate availability.
- If `HAS_GST` is false, `GatewayVideo` initialization should log a warning or raise an error if specifically requested.
- Ensure the module can be imported even if dependencies are missing.

### `conversation_app/gateway.py`
- Move `from .gateway_video import GatewayVideo` from top-level to inside `ReachyGateway.__init__` or make it conditional.
- Add `ENABLE_VISION` check in `ReachyGateway.__init__`.
- Only initialize `self.gateway_video` if `ENABLE_VISION` is true.
- Update `run()`: Only start video capture if `self.gateway_video` is initialized.
- Update `cleanup()`: Only cleanup video if `self.gateway_video` is initialized.
- Update `main()`: Log video status (Enabled/Disabled).

### `conversation_app/reachy_camera_example.py`
- Wrap imports in `try...except` to prevent immediate crash if run without dependencies (optional, but good practice since user mentioned commenting out imports).

## Verification Plan

### Automated Tests
- None (Vision is hard to test automatically without dependencies).

### Manual Verification
1.  **Verify Disabled State (Default)**:
    - Ensure `opencv-python` and `PyGObject` are NOT installed (or simulate by renaming/hiding).
    - Run `python -m conversation_app.gateway` (or `app.py`).
    - Verify app starts without `ImportError`.
    - Verify logs show "Video processing component: Disabled" (or similar).
    - Verify no video files are created in `/videos`.

2.  **Verify Enabled State**:
    - Install `opencv-python` and `PyGObject`.
    - Set `ENABLE_VISION=true`.
    - Run `python -m conversation_app.gateway`.
    - Verify app starts and initializes video.
    - Verify logs show "Video processing component initialized".
    - Verify frames are captured in `/videos`.
