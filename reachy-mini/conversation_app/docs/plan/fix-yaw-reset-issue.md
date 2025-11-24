# Investigation: Yaw Reset Issue

## Issue Description
The user reported that `move_to` commands reset each other.
Example:
1. `move_to(yaw=120)` -> Robot moves correctly (User says "good").
2. `move_to(roll=10)` -> Robot tilts head, but yaw resets (likely to near 0 or a much smaller value).

## Root Cause Analysis

I have analyzed `conversation_app/reachy_controller.py` and identified two critical bugs that explain this behavior.

### Bug 1: `apply_safety_to_movement` Logic Error
The `apply_safety_to_movement` function attempts to distribute yaw between the head and the body when limits are exceeded, but it fails to correctly clamp the original values.

```python
# Current Code (Lines 427-432)
if abs(yaw) > HEAD_YAW_LIMIT:
    overflow = yaw - np.sign(yaw) * HEAD_YAW_LIMIT
    safe_yaw = yaw  # <--- ERROR: safe_yaw is NOT clamped! It remains 120.
    safe_body_yaw = body_yaw + overflow
```

If `yaw` is 120 and `body_yaw` is 0:
- `HEAD_YAW_LIMIT` = 40.
- `overflow` = 80.
- `safe_yaw` = 120 (Should be 40).
- `safe_body_yaw` = 80.

Then, it checks `safe_body_yaw` limit (25):
```python
# Current Code (Lines 439-444)
if abs(safe_body_yaw) > BODY_YAW_LIMIT:
    body_overflow = safe_body_yaw - np.sign(safe_body_yaw) * BODY_YAW_LIMIT
    safe_body_yaw = safe_body_yaw # <--- ERROR: safe_body_yaw is NOT clamped! It remains 80.
    safe_yaw = safe_yaw + body_overflow
```
- `BODY_YAW_LIMIT` = 25.
- `body_overflow` = 80 - 25 = 55.
- `safe_body_yaw` = 80 (Should be 25).
- `safe_yaw` = 120 + 55 = 175.

**Result**: The code returns `safe_yaw=175` and `safe_body_yaw=80`.
The robot likely attempts to move to these extreme positions (or hits hardware limits).

### Bug 2: `_current_body_yaw` Tracking Failure
The `ReachyController` tracks `_current_body_yaw` to know where the body is, since `ReachyMini` doesn't seem to provide a way to read the current body yaw directly (or it's not being used).

```python
# Current Code (Line 284)
self._current_body_yaw = target_body_yaw
```

This updates the internal state with the *requested* `target_body_yaw` (which is 0 in the first `move_to(yaw=120)` call), **ignoring** the fact that `apply_safety_to_movement` might have significantly changed the actual body yaw sent to the robot (e.g., to 80 or 25).

**Scenario**:
1. `move_to(yaw=120)`:
   - `target_body_yaw` = 0.
   - `self._current_body_yaw` becomes 0.
   - Robot (due to Bug 1) receives command for Body=80 (or 25 if clamped by hardware).
   - Robot physically moves body to ~25-80.

2. `move_to(roll=10)`:
   - `yaw` and `body_yaw` are `None`.
   - `_get_current_state()` is called.
   - It reads `head_yaw` from the robot (e.g., 40).
   - It reads `body_yaw` from `self._current_body_yaw` -> **returns 0** (Incorrect! Robot is at ~25+).
   - `target_yaw` = 40.
   - `target_body_yaw` = 0.
   - `apply_safety_to_movement(yaw=40, body_yaw=0)` -> No overflow.
   - Robot moves to Head=40, Body=0.
   - **Visual Result**: The body swings back from ~25+ to 0. The total yaw drops from ~65+ to 40. This looks like a reset.

## Fix Plan

### 1. Fix `apply_safety_to_movement`
Modify the function to correctly clamp values when overflow occurs.

```python
if abs(yaw) > HEAD_YAW_LIMIT:
    overflow = yaw - np.sign(yaw) * HEAD_YAW_LIMIT
    safe_yaw = np.sign(yaw) * HEAD_YAW_LIMIT  # <--- FIX: Clamp it
    safe_body_yaw = body_yaw + overflow

if abs(safe_body_yaw) > BODY_YAW_LIMIT:
    body_overflow = safe_body_yaw - np.sign(safe_body_yaw) * BODY_YAW_LIMIT
    safe_body_yaw = np.sign(safe_body_yaw) * BODY_YAW_LIMIT # <--- FIX: Clamp it
    safe_yaw = safe_yaw + body_overflow
```

### 2. Fix `_current_body_yaw` Tracking
Update `self._current_body_yaw` with the *actual* value sent to the robot, after safety calculations.

In `move_to` and `move_smoothly_to`:
```python
# ... calculate safe_body_yaw ...
self.mini.goto_target(..., body_yaw=safe_body_yaw)
self._current_body_yaw = safe_body_yaw  # <--- FIX: Update with the value actually used
```

### 3. Verification
1.  **Manual Test**:
    - Command: `move_to(yaw=60)` (Should split: Head=40, Body=20).
    - Check `_current_body_yaw` (Should be 20).
    - Command: `move_to(roll=10)`.
    - Check that `body_yaw` stays at 20.
