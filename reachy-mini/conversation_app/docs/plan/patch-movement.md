
# Plan: Patch Movement Mode (Introduce Null Values)

## Goal
Modify `move_to`, `move_smoothly_to`, and `move_cyclically` in `conversation_app/reachy_controller.py` 
to accept `None` values for movement parameters (roll, pitch, yaw, antennas, body_yaw).
When a parameter is `None`, the robot should maintain its current position for that joint/axis 
instead of resetting to a default (usually 0.0).

## Current State
- `move_to`, `move_smoothly_to`, `move_cyclically` have default values of 0.0 (or [0.0, 0.0]).
- Calling these methods with partial arguments resets unspecified arguments to 0.
- `ReachyMini` (the lower-level driver) supports `None` in `set_target` and `goto_target` for some parameters, 
  but `ReachyController` constructs full poses which requires all values.

## Proposed Changes

1.  **Update `ReachyController` Class (`conversation_app/reachy_controller.py`)**:
    *   Import `Rotation` from `scipy.spatial.transform` to convert matrix to Euler angles.
    *   Add state tracking for `body_yaw` (as it's not easily readable from `ReachyMini`? 
        Actually `ReachyMini` might not expose it, so we'll track `self._current_body_yaw` initialized to 0.0).
    *   Implement a helper method `_get_current_state()`:
        *   Get head pose matrix from `self.mini.get_current_head_pose()`.
        *   Convert matrix to roll, pitch, yaw (degrees).
        *   Get antennas positions from `self.mini.get_present_antenna_joint_positions()` (convert to degrees).
        *   Return `(roll, pitch, yaw, antennas, body_yaw)`.

2.  **Modify `move_to`**:
    *   Change default arguments for `roll`, `pitch`, `yaw`, `antennas`, `body_yaw` to `None`.
    *   Call `_get_current_state()` to get current values.
    *   For each argument:
        *   If `None`, use the current value.
        *   If provided, use the provided value.
    *   Update `self._current_body_yaw` if `body_yaw` changes.
    *   Pass the resolved values to `apply_safety_to_movement` and then `self.mini.goto_target`.

3.  **Modify `move_smoothly_to`**:
    *   Change default arguments to `None`.
    *   Call `_get_current_state()`.
    *   Resolve target values (use current if None).
    *   In the movement loop:
        *   For `None` parameters (that are now resolved to current values), 
            we need to decide if we apply the "smooth movement" function (sine wave) or keep them static.
            *   If we want to "move smoothly to" a target, and the target is the current position, 
                `smooth_movement` (which generates a sine wave from 0 to Target?) might cause a dip?
            *   Wait, `smooth_movement` implementation: `max_angle * sin(...)`.
                This implies oscillation around 0.
                If we want to hold position at 20, `20 * sin` will oscillate.
                This suggests `move_smoothly_to` is designed for *gestures* (relative movements) rather than absolute positioning?
                The user says "when the model requests to nod the head, it doesn't reset the rest of the movement".
                This implies `move_smoothly_to` is used for nods.
                If I nod (pitch), I want yaw to stay at 20 (if it was at 20).
                If I pass `yaw=None`, I want `yaw` to stay at 20.
                If I resolve `yaw` to 20, and pass it to `smooth_movement`, it will oscillate 0->20->0.
                That's NOT what we want. We want it to stay at 20.
            *   So, for `None` parameters, we should bypass `smooth_movement` and use the constant current value.
    *   Update `self._current_body_yaw`.

4.  **Modify `move_cyclically`**:
    *   Change defaults to `None`.
    *   Pass `None` values through to `move_smoothly_to`.
    *   (Since `move_smoothly_to` will handle `None` by keeping constant, this works).

5.  **Update `ActionHandler` (`conversation_app/action_handler.py`)**:
    *   Update `_build_tools_context` to reflect that parameters are optional and default to "current value" (or None).
    *   (Optional) The LLM prompt already says "default: 0.0", we might want to update it to say "default: keep current".

## Verification Plan
1.  **Manual Test Script**: run the docker and try to nod the head while yawing.
