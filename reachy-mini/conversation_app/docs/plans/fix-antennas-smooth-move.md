# Fix Antennas Smooth Move

## Goal Description
The goal is to ensure that antenna movements continue smoothly even when other actions (like head movements or interjections) occur, and to resolve conflicts between continuous movement and the robot's sleep state. Additionally, we want to distinguish between direct single-parameter actions and complex preset movements.

## User Review Required
> [!IMPORTANT]
> **Logic Change**: `move_smoothly_to` will now use the **current target pose** from `MovementManager` (if available) as the default for unspecified parameters, instead of the **current physical state**. This ensures that if antennas are moving to a target, a subsequent head move command won't "freeze" the antennas at their current intermediate position.

## Proposed Changes

### 1. Fix `move_smoothly_to` Interruption Logic
Currently, `ReachyController.move_smoothly_to` uses `get_current_state()` to fill in missing parameters. If a component (e.g., antennas) is in the middle of a movement, using its current position as the new target effectively stops it.

**Changes:**
- Modify `ReachyController.move_smoothly_to`:
    - Check if `self.movement_manager` is available.
    - If yes, retrieve the *current target pose* from `movement_manager.base_layer.target_pose`.
    - Use this target pose to fill in `None` parameters.
    - Only use `get_current_state()` if `MovementManager` is not running or for initialization.

### 2. Resolve Sleep Conflict
`MovementManager` continues running its control loop even when the robot is turned off, potentially waking it up or fighting with the sleep command.

**Changes:**
- Modify `MovementManager._loop`:
    - Check `self.controller.reachy_is_awake`.
    - If `False`, skip sending commands (or send only once to ensure sleep, then pause).
    - Alternatively, `turn_off_smoothly` should call `movement_manager.stop()` or `movement_manager.pause()`.
    - **Decision**: Update `MovementManager` to respect `reachy_is_awake` flag. If not awake, it should not send `set_target` commands.

### 3. Smooth Idle Transitions
Antenna stuttering during interjections might be caused by abrupt enabling/disabling of the `IdleLayer`.

**Changes:**
- Update `IdleLayer` (in `movement_layers.py`) to support smooth transitions (fade in/out) when enabled/disabled.
- Ensure `app.py` calls `enable_idle` in a way that triggers this smooth transition.

### 4. Separate Direct Actions vs. Sets
With the fix in #1, `move_antennas` and `set_target_head_pose` will become independent. Calling `set_target_head_pose` will not stop `move_antennas`.

**Changes:**
- No new actions needed strictly for this, but the fix in #1 enables the desired behavior.
- "Dance set" can be implemented as a new action script that sequences multiple `move_smoothly_to` calls, which is already supported by the architecture.

## Verification Plan

### Automated Tests
- **Unit Test for `move_smoothly_to`**:
    - Mock `MovementManager`.
    - Set a target for antennas.
    - Call `move_smoothly_to(roll=10)`.
    - Verify that the new target sent to `MovementManager` preserves the antenna target, rather than using the current antenna position.

### Manual Verification
1.  **Antenna Independence**:
    - Command: "Move antennas to 30 degrees over 5 seconds."
    - Immediately Command: "Look left."
    - **Expected**: Head turns left, antennas *continue* moving to 30 degrees without stopping/stuttering.
2.  **Sleep Conflict**:
    - Command: "Turn off robot."
    - **Expected**: Robot goes to sleep and *stays* asleep. No jitter or waking up due to background loop.
3.  **Interjection Stutter**:
    - Start a long antenna move.
    - Speak to the robot to trigger an interjection (which enables idle).
    - **Expected**: Transition to idle (or superposition of idle) is smooth.
