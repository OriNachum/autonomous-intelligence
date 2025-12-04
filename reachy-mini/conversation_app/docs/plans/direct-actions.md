# Plan: Upgrade Actions to Direct Control Scripts

## Goal
Upgrade all action scripts in `conversation_app/actions/scripts/` to match the robustness and direct control pattern of `wobble_head.py`. This involves:
1.  **Robust Parameter Parsing**: Explicitly casting parameters to expected types (float, int, etc.) and handling `ValueError`/`TypeError`.
2.  **Sensible Defaults**: Providing fallback values for missing or invalid parameters.
3.  **Error Handling**: Gracefully handling execution errors.
4.  **Direct Control**: Ensuring scripts directly manage the robot's state via API calls, minimizing reliance on opaque upstream logic.

## Current State Analysis
| Script | Status | Issues Identified |
| :--- | :--- | :--- |
| `wobble_head.py` | **Gold Standard** | Reference implementation. Robust parsing, error handling. |
| `nod_head.py` | Needs Upgrade | Lacks explicit type casting for `duration`, `angle`. |
| `shake_head.py` | Needs Upgrade | Lacks explicit type casting. |
| `move_head.py` | Needs Upgrade | Lacks explicit type casting for coordinates/angles. |
| `look_at_direction.py` | Needs Upgrade | Lacks robust parsing. |
| `express_emotion.py` | Needs Upgrade | Lacks robust parsing. |
| `perform_gesture.py` | Needs Upgrade | Hardcoded values, lacks robust parsing, duplicates logic. |
| `speak.py` | Good | Simple, but could benefit from standard error handling pattern. |
| `tilt_head.py` | Needs Upgrade | Lacks explicit type casting. |
| `move_antennas.py` | Needs Upgrade | Lacks explicit type casting. |
| `reset_head.py` | Needs Upgrade | Lacks explicit type casting. |
| `reset_antennas.py` | Needs Upgrade | Lacks explicit type casting. |
| `turn_on/off_robot.py` | Good | Simple, but verify consistency. |
| `get_*.py` | Good | Mostly read-only, check for parameter handling if any. |

## Proposed Changes

### 1. Standardize Parameter Parsing
Apply the following pattern to all scripts:
```python
try:
    param_value = float(params.get('param_name', default_value))
except (ValueError, TypeError):
    param_value = default_value
```

### 2. Update Specific Scripts

#### `nod_head.py`
- Add robust parsing for `duration` and `angle`.
- Ensure `angle` is treated as float.

#### `shake_head.py`
- Add robust parsing for `duration` and `angle`.

#### `move_head.py`
- Add robust parsing for `x`, `y`, `z`, `roll`, `pitch`, `yaw`, `duration`.
- Handle `degrees` and `mm` booleans safely.

#### `perform_gesture.py`
- Refactor to use robust parsing.
- Consider externalizing gesture definitions or making them more configurable if possible, but for now, just fix the parsing.

#### `look_at_direction.py`
- Validate `direction` against allowed values.
- Robust parsing for `duration`.

#### `express_emotion.py`
- Validate `emotion` against allowed values.

### 3. Verification Plan

#### Automated Verification
- Create a test script `tests/verify_actions.py` (or similar) that imports each script's `execute` function and calls it with:
    - Valid parameters (should succeed).
    - Invalid parameters (strings where floats expected) -> should use defaults/handle gracefully.
    - Missing parameters -> should use defaults.
- Mock `make_request`, `create_head_pose`, and `tts_queue` to avoid actual robot calls during verification.

#### Manual Verification
- Run the `conversation_app` and trigger actions via voice/text to ensure they still work on the real robot (or simulator).
