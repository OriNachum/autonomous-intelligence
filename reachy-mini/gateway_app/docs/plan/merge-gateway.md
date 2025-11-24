# Merge Gateway and Conversation Apps

## Goal
Merge `gateway_app` functionality into `conversation_app` so that `ReachyGateway` runs within the `conversation_app` process. This simplifies the architecture and allows direct communication between the conversation logic and the gateway (hearing/daemon management).

## User Review Required
> [!IMPORTANT]
> This change removes the standalone `reachy-gateway` service from Docker. `reachy-conversation` will now handle hardware interaction (microphone, robot connection), requiring privileged access.

## Proposed Changes

### Docker Configuration
#### [MODIFY] [docker-compose-vllm.yml](file:///home/thor/git/autonomous-intelligence/reachy-mini/docker-compose-vllm.yml)
- Remove `reachy-gateway` service.
- Update `reachy-conversation` service:
    - Add `privileged: true`.
    - Set `network_mode: host`.
    - Add devices: `/dev/bus/usb`, `/dev/snd`.
    - Add volumes: `/dev/shm`, `/dev`, and mount `./gateway_app:/app/gateway_app`.
    - Update `command` to install requirements from both `conversation_app` and `gateway_app`.
    - Set `PYTHONPATH` to include `/app/gateway_app` so imports work without code changes in `gateway_app`.

### Gateway App
#### [MODIFY] [gateway_app/gateway.py](file:///home/thor/git/autonomous-intelligence/reachy-mini/gateway_app/gateway.py)
- Update `ReachyGateway` class:
    - Add `event_callback` parameter to `__init__`.
    - Update `emit_event` to call `event_callback` (if set) in addition to/instead of socket emission.
    - Ensure `run` method is compatible with being run as an `asyncio.Task` (it already seems to be).
    - Allow disabling socket server if not needed (optional, but good for cleanup).

### Conversation App
#### [MODIFY] [conversation_app/app.py](file:///home/thor/git/autonomous-intelligence/reachy-mini/conversation_app/app.py)
- Import `ReachyGateway`.
- Update `ConversationApp` class:
    - In `initialize`:
        - Instantiate `ReachyGateway` with a callback pointing to `self.on_gateway_event`.
    - Add `on_gateway_event` method to route events to `on_speech_started`, `on_speech_stopped`, etc.
    - In `run`:
        - Start `self.gateway.run()` as a background task.
    - In `cleanup`:
        - Stop the gateway.

## Verification Plan

### Manual Verification
1.  **Build and Start**:
    ```bash
    docker compose -f docker-compose-vllm.yml up -d --build reachy-conversation
    ```
2.  **Check Logs**:
    ```bash
    docker compose -f docker-compose-vllm.yml logs -f reachy-conversation
    ```
    - Verify "Reachy Gateway starting..." appears in logs.
    - Verify "Conversation App initialized" appears.
    - Verify "Reachy Mini daemon spawned successfully".
3.  **Test Interaction**:
    - Speak to the robot.
    - Verify logs show "Speech detected" (from Gateway) and "Processing speech event" (from Conversation App).
    - Verify response is generated.
