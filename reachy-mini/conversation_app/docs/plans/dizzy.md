# Plan: Dizzy Head Action

## Goal
Rename the `wobble_head` action to `dizzy` and improve its implementation to produce a "dizzy" effect (moving in slow circles) instead of the current "spasm" behavior.

## User Review Required
- **Breaking Change**: The action `wobble_head` will be renamed to `dizzy`. Any existing prompts or scripts using `wobble_head` will need to be updated.

## Proposed Changes

### Action Definition and Script
#### [RENAME] `wobble_head` -> `dizzy`
- Rename `conversation_app/actions/scripts/wobble_head.py` to `conversation_app/actions/scripts/dizzy.py`.
- Rename `conversation_app/actions/wobble_head.json` to `conversation_app/actions/dizzy.json`.

### [MODIFY] `conversation_app/actions/dizzy.json`
- Update `name` to `"dizzy"`.
- Update `description` to "Make the robot look dizzy by moving its head in slow circles."
- Update `script_file` to `"dizzy.py"`.
- Update default parameters:
    - `speed`: Change default from `1.0` to `0.2` (circles per second) for a slower, dizzier effect.
    - `duration`: Change default from `2.0` to `5.0` seconds to allow for a full rotation at slow speed.
    - `radius`: Keep default at `15.0` degrees.

### [MODIFY] `conversation_app/actions/scripts/dizzy.py`
- Update docstrings to reflect the new name and behavior.
- Implement smooth circular motion logic:
    - Ensure `step_duration` is not too small (e.g., minimum 0.1s) to avoid "spasms" caused by flooding the control loop.
    - Calculate `points_per_circle` dynamically based on `speed` and a target update rate (e.g., 10Hz).
    - Logic:
        ```python
        # Target update rate (Hz)
        UPDATE_RATE = 10
        step_duration = 1.0 / UPDATE_RATE
        
        # Total steps
        total_steps = int(duration * UPDATE_RATE)
        
        for i in range(total_steps):
            # Calculate current time
            t = i * step_duration
            
            # Calculate angle (2 * pi * speed * t)
            angle = 2 * math.pi * speed * t
            
            # Calculate roll and pitch
            roll = radius * math.sin(angle)
            pitch = radius * math.cos(angle)
            
            # Execute move
            # ...
        ```

### [MODIFY] `conversation_app/actions/tools_index.json`
- Add the `dizzy` tool to the index.
- (Note: `wobble_head` was not present in the index, so no removal is strictly necessary, but we will ensure `dizzy` is added).

## Verification Plan

### Automated Tests
- None.

### Manual Verification
1.  **Restart Application**: Ensure the new action is loaded.
2.  **Trigger Action**:
    - Say "Act dizzy" or "I feel dizzy" to the robot.
    - Verify the robot moves its head in slow, smooth circles.
3.  **Check Parameters**:
    - Verify `speed`, `radius`, and `duration` parameters work as expected.
