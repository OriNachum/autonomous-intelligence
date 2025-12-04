# Plan: Parameterized Locations (Return, Back, DOA)

This plan outlines the changes required to add parameterized inputs ("return", "back", "DOA") to the action handler for Reachy.

## Goal
Enable the robot to:
1.  **Return**: Go back to the state before the current sequence of movements began.
2.  **Back**: Go back to the previous location within the current movement sequence.
3.  **DOA**: Orient `yaw`, `body_yaw`, and `antennas` towards the Direction of Audio.

## Proposed Changes

### 1. `conversation_app/mappings.py`
*   **Update `name_to_value`**:
    *   Allow "return", "back", and "doa" (case-insensitive) to pass through without raising a `ValueError`.
    *   These will be handled dynamically by the `ActionHandler`.

### 2. `conversation_app/reachy_controller.py`
*   **Update `get_current_doa`**:
    *   Ensure it provides the DOA angle in a format easily convertible to Reachy's coordinate system (degrees, centered on forward).
    *   Currently returns radians.
*   **Add `get_doa_yaw()`**:
    *   Helper to get the current DOA as a yaw angle in degrees.

### 3. `conversation_app/action_handler.py`
*   **Update `ActionHandler` class**:
    *   **`execute` method**:
        *   Capture `initial_state` (roll, pitch, yaw, antennas, body_yaw) before processing the list of commands.
        *   Initialize `state_history` list with `initial_state`.
    *   **`_resolve_parameter` method (New)**:
        *   Create a helper to resolve parameter values, handling "return", "back", and "DOA".
        *   **"return"**: Returns the value from `initial_state`.
        *   **"back"**: Returns the value from the last item in `state_history`.
        *   **"DOA"**: 
            *   For `yaw` and `body_yaw`: Fetches current DOA angle from `gateway`/`controller`.
            *   For `antennas`: Define a behavior (e.g., point towards sound or 'alert' pose).
    *   **Loop Update**:
        *   Inside the command loop, before normalization/execution:
            *   Resolve parameters using `_resolve_parameter`.
            *   Update `state_history` with the state *after* the move (or assume target state is reached).
            *   Actually, "back" implies going to where we *were*. So we should push the *current* state to history before moving.

### 4. `conversation_app/agents/action-handler/action-handler.system.md`
*   **Update Documentation**:
    *   Add "return", "back", and "DOA" to the list of valid values for relevant parameters.
    *   Add examples showing how to use them (e.g., "Look at DOA", "Look North then Back").

## Verification Plan (Manual)
1.  **Manual Verification**:
    *   Test "return": Move Head -> Move Head -> Return. Verify it goes back to start.
    *   Test "back": Move Head -> Move Head -> Back. Verify it goes to intermediate position.
    *   Test "DOA": Make noise -> Command "yaw='DOA'". Verify robot looks at sound.
