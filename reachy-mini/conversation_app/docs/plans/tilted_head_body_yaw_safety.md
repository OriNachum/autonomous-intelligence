# Plan: Tilted Head Body Yaw Safety

## Goal
Implement a safety rule that restricts the relative yaw between the head and body when the head is tilted.
Specifically: When head roll (tilt) exceeds a threshold `X`, the allowed difference between head yaw and body yaw is reduced to `Y`.
This ensures that if the head is tilted, the body must rotate to keep the head aligned, preventing collisions with the shoulders or mechanical stress.

## User Review Required
> [!IMPORTANT]
> **Assumption**: The requirement "When head is tilted over x, body_yaw allowed is top y" is interpreted as "When head tilt > x, the maximum *relative* yaw (head_yaw - body_yaw) is y". This forces the body to move if the head moves, satisfying the condition "so the body will move if the head is moving while tilted".

## Proposed Changes

### [conversation_app]

#### [MODIFY] [safety_manager.py](file:///home/thor/git/autonomous-intelligence/reachy-mini/conversation_app/safety_manager.py)
1.  **Update `SafetyConfig`**:
    *   Add `TILT_SAFETY_THRESHOLD` (default: 15.0 degrees).
    *   Add `TILT_MAX_YAW_DIFFERENCE` (default: 10.0 degrees).
2.  **Update `SafetyManager`**:
    *   Modify `_enforce_yaw_difference` (or the validation pipeline) to check `head_roll`.
    *   If `abs(head_roll) > TILT_SAFETY_THRESHOLD`, use `TILT_MAX_YAW_DIFFERENCE` instead of the standard `MAX_YAW_DIFFERENCE`.

## Verification Plan

### Automated Tests
*   **New Unit Test**: Add a test case in `conversation_app/tests/test_safety_manager.py` that:
    *   Sets up a scenario with `head_roll > TILT_SAFETY_THRESHOLD`.
    *   Sets `head_yaw` and `body_yaw` such that their difference is greater than `TILT_MAX_YAW_DIFFERENCE` but less than `MAX_YAW_DIFFERENCE`.
    *   Asserts that the `body_yaw` is adjusted to satisfy the stricter limit.
    *   Command: `pytest conversation_app/tests/test_safety_manager.py`

### Manual Verification
*   **Script**: Create a script `verify_tilt_safety.py` that:
    1.  Initializes `ReachyController`.
    2.  Moves head to a tilted position (e.g., Roll = 20).
    3.  Moves head Yaw to 30 (while Body Yaw is 0).
    4.  Checks if Body Yaw automatically moves to ~20 (to keep diff <= 10).
