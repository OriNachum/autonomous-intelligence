# Safety Redesign Plan

## Goal Description
Redesign the safety mechanism for the Reachy robot to prioritize head movement ("Head is Self") and implement dynamic collision avoidance between the head and the body. This will be implemented in a new external module to keep the controller clean and configurable.

## User Review Required
> [!IMPORTANT]
> **Head Priority**: The new logic fundamentally changes how the robot moves. The head's requested position will be treated as the "truth", and the body will move *only* to accommodate the head or if explicitly commanded (and safe).
>
> **Collision Logic**: The system will actively move the body out of the way if the head tilts into a potential collision zone.

## Proposed Changes

### New Module: `conversation_app/safety_manager.py`
This new file will encapsulate all safety logic.

#### Key Features:
1.  **Configuration**: A class or dictionary to define:
    *   `HEAD_YAW_LIMIT`: Max yaw for head relative to body.
    *   `BODY_YAW_LIMIT`: Max absolute yaw for body.
    *   `COLLISION_ZONES`: Definitions of where the head might hit the body (e.g., high roll + specific pitch).
    *   `SAFE_MARGINS`: Buffer zones to prevent touching.

2.  **`SafetyManager` Class**:
    *   `__init__(config)`: Load configuration.
    *   `validate_movement(current_state, target_state)`: The main entry point.
    *   `_resolve_head_body_collision(head_state, body_state)`: Specific logic for the "Head is Self" rule.

### Logic Description

#### 1. Head Priority ("Self")
*   **Input**: Target Head (Roll, Pitch, Yaw) + Target Body Yaw.
*   **Rule**: If the Target Head position is valid within global limits but conflicts with the *current* or *target* Body Yaw, the **Body Yaw is adjusted** to make the Head position possible.

#### 2. Collision Avoidance Scenarios

*   **Scenario A: Head Moving, Body Stationary**
    *   *Condition*: Head wants to tilt (Roll) or Pitch, but the current Body Yaw makes it unsafe (e.g., shoulder collision).
    *   *Action*: Automatically move Body Yaw to a "Safe Zone" that allows the Head Tilt/Pitch.

*   **Scenario B: Head Tilting, Body Moving**
    *   *Condition*: Body is moving (e.g., to a new target), and Head is tilted.
    *   *Action*: Limit the Body Yaw target so it doesn't crash into the tilted head. The Head stays tilted (priority), the Body stops early.

*   **Scenario C: Body Rotated, Head Tilting**
    *   *Condition*: Body is already at an extreme angle, Head tries to tilt.
    *   *Action*: Body moves back towards center/neutral to allow the Head to tilt safely.

### Integration: `conversation_app/reachy_controller.py`

#### [MODIFY] `reachy_controller.py`
*   Import `SafetyManager` from `safety_manager.py`.
*   Initialize `self.safety_manager` in `__init__`.
*   Replace the existing `apply_safety_to_movement` method with a call to `self.safety_manager.validate_movement`.

## Verification Plan

### Automated Tests
*   Create `tests/test_safety_manager.py`.
*   Test cases for each scenario:
    *   Head tilt forces body move.
    *   Body move restricted by head tilt.
    *   Extreme head yaw rotates body.

### Manual Verification
*   Run the robot and issue commands:
    *   "Look down and tilt left" -> Verify body moves if needed.
    *   "Turn body left" while head is tilted -> Verify body stops before hitting head.
