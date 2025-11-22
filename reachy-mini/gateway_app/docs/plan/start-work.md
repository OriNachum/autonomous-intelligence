# Plan: Create Reachy Gateway

## Goal
Refactor `hearing_app` and `daemon_app` into a unified `reachy_gateway` service.
This service will:
1.  Be the central entry point for the Reachy Mini robot.
2.  Manage the `reachy-mini-daemon` lifecycle (start/stop) via the application itself.
3.  Run the Hearing logic (VAD, STT, DOA).
4.  Be extensible for future events (Vision, Motors).
5.  Maintain robust startup and shutdown scripts.

## Architecture

*   **Service Name**: `reachy_gateway` (formerly `reachy-hearing` / `reachy-daemon`)
*   **Main Application**: `gateway_app/gateway.py` (Python)
    *   Initializes `ReachyMini` with `spawn_daemon=True`.
    *   Runs the Event Loop (Hearing, etc.).
    *   Handles Signals (SIGTERM, SIGINT) for graceful shutdown.
*   **Container**: Defined in `docker-compose-vllm.yml`.

## Implementation Steps

### 1. Prepare Gateway Application
*   [ ] **Consolidate Code**: Move necessary files from `hearing_app` to `gateway_app` (or ensure `gateway_app` can import them).
    *   `hearing_event_emitter.py` -> Refactor into `gateway.py`.
    *   `doa_detector.py`, `vad_detector.py`, `whisper_stt.py` -> Move/Copy to `gateway_app` or a shared `lib` folder.
*   [ ] **Create `gateway.py`**:
    *   Based on `hearing_event_emitter.py`.
    *   **Initialization**:
        *   Initialize `DoADetector` (which initializes `ReachyMini(spawn_daemon=True)`) *before* starting the event loop.
        *   Ensure `ReachyMini` is accessible to other modules if needed.
    *   **Signal Handling**:
        *   Register signal handlers for SIGINT and SIGTERM.
        *   On signal, call `cleanup()`.
    *   **Cleanup**:
        *   Call `DoADetector.cleanup()` (which closes `ReachyMini` and stops daemon).
        *   Close sockets and audio streams.

### 2. Update Scripts
*   [ ] **Update `gateway_app/start_gateway.sh`**:
    *   Remove explicit `reachy-mini-daemon` startup command.
    *   Install dependencies (keep `alsa-utils`, `portaudio`, etc.).
    *   Execute `python3 gateway.py`.
    *   Keep the `trap` to ensure `shutdown_gateway.sh` is called or signals are passed.
*   [ ] **Update `gateway_app/shutdown_gateway.sh`**:
    *   Update to find and kill the `gateway.py` process.
    *   Ensure it waits for graceful exit before force killing.

### 3. Docker Configuration
*   [ ] **Update `docker-compose-vllm.yml`**:
    *   Rename/Update service to `reachy-gateway`.
    *   Point build context to `gateway_app`.
    *   Ensure volumes and devices are correctly mapped (needs access to USB/Audio).

### 4. Verification
*   [ ] **Test Startup**:
    *   Run `start_gateway.sh`.
    *   Verify `reachy-mini-daemon` process is running (spawned by Python).
    *   Verify Hearing service is active.
*   [ ] **Test Shutdown**:
    *   Send SIGTERM (Ctrl+C).
    *   Verify Python app stops.
    *   Verify `reachy-mini-daemon` stops.
*   [ ] **Test Functionality**:
    *   Verify DOA and Speech events are still emitted.

## Future Extensibility
*   The `gateway.py` structure should allow adding new async tasks for:
    *   `MotorEventMonitor` (checking load/movement).
    *   `VisionEventMonitor` (camera processing).
