# Reachy Antenna Movement Modes Plan

## Goal
Add "states" or "modes" to Reachy so that:
1.  **Waiting Mode**: Antennas move continuously in a sinusoidal pattern (15 to -15 degrees) when the robot is listening or waiting.
2.  **Static Mode**: Antennas stop moving when the robot is performing an action or speaking.

## User Review Required
> [!IMPORTANT]
> **Behavior Confirmation**:
> - **Listening (User speaking)**: Antennas MOVE (Waiting Mode).
> - **Thinking (Processing)**: Antennas MOVE (Waiting Mode).
> - **Robot Speaking/Acting**: Antennas STOP (Static Mode).
> - **Idle**: Antennas MOVE (Waiting Mode) - assuming "listening" covers the idle state waiting for input.

## Proposed Changes

### 1. Create `MovementManager`
**File**: `conversation_app/movement_manager.py` (NEW)

Create a class `MovementManager` that runs a background thread to control antenna movements.

-   **Modes**:
    -   `STATIC`: No background movement.
    -   `WAITING`: Sinusoidal movement of antennas.
-   **Logic**:
    -   Run a control loop (e.g., 50Hz).
    -   In `WAITING` mode:
        -   Calculate target antenna positions using `sin(time)` function.
        -   Range: -15 to +15 degrees (absolute). *Assumption: Absolute degrees, centered at 0 or current neutral.*
        -   Use `ReachyController.mini.set_target` directly for smooth, non-blocking updates.
        -   Ensure thread safety with other actions.
-   **Safety**:
    -   Check if an explicit action is running (via `ActionHandler` or flag) to avoid conflict.

### 2. Integrate into `ConversationApp`
**File**: `conversation_app/app.py`

-   **Initialize**: Instantiate `MovementManager` in `initialize()`, passing the `gateway.reachy_controller`.
-   **State Transitions**:
    -   `on_speech_started` (User speaks): Set mode to `WAITING`.
    -   `on_speech_stopped` (User done): Keep mode `WAITING` (Thinking).
    -   `process_message` (Before Robot speaks/acts): Set mode to `STATIC`.
    -   `process_message` (After Robot finishes): Set mode to `WAITING`.

### 3. Update `ActionHandler` (Optional/Advanced)
**File**: `conversation_app/action_handler.py`

-   Ensure that when an action (like `move_antennas` tool) is called, it overrides the background movement.
-   The `MovementManager` should probably have a `pause()` method that `ActionHandler` calls during execution.

## Implementation Details

### `MovementManager` Class Structure
```python
class MovementManager:
    def __init__(self, reachy_controller):
        self.controller = reachy_controller
        self.mode = "STATIC"
        self.running = False
        self._thread = None

    def start(self):
        self.running = True
        self._thread = threading.Thread(target=self._loop)
        self._thread.start()

    def set_mode(self, mode):
        self.mode = mode

    def _loop(self):
        while self.running:
            if self.mode == "WAITING":
                # Calculate sine wave
                # Update antennas
                pass
            time.sleep(0.02)
```

## Verification Plan

### Manual Verification
1.  **Start the App**: Run `python conversation_app.py`.
2.  **Observe Idle**: Verify antennas are moving (Waiting Mode).
3.  **Speak to Robot**: Verify antennas continue moving while you speak.
4.  **Robot Responds**: Verify antennas STOP moving while the robot speaks or performs an action.
5.  **Return to Idle**: Verify antennas resume moving after the robot finishes.

### Automated Tests
-   Create a test script `tests/test_movement_manager.py` that instantiates `MovementManager` with a mock controller and asserts that `set_target` is called with varying values in `WAITING` mode and not called in `STATIC` mode.
