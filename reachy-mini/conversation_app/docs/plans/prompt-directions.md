# Plan: Update Directions to Natural Language

## Goal
Update the robot's direction understanding and reporting to use natural language terms ("left", "right", "front", "up", "down") instead of compass directions ("North", "East", "West"). Additionally, introduce the concept of "speaker" as the source of audio in the system prompt and application logic.

## Proposed Changes

### 1. Update Mappings (`conversation_app/mappings.py`)
Modify the direction conversion logic to use natural terms.

#### [MODIFY] [mappings.py](file:///home/thor/git/autonomous-intelligence/reachy-mini/conversation_app/mappings.py)
- **Update `degrees_to_compass` function**:
    - Rename to `degrees_to_direction` (or keep name for compatibility but change output).
    - Change output mapping:
        - North (0°) -> "front"
        - East (90°) -> "right" (Note: Reachy's coordinate system might differ, need to verify. In `mappings.py`: `East=90°, West=-90°`. `Reachy: Max Right=-45°, Max Left=+45°`. `reachy_yaw = -1 * (compass_angle / 2)`. So East (90) -> -45 (Right). West (-90) -> 45 (Left). North (0) -> 0 (Front).)
        - West (-90°) -> "left"
        - South (180°) -> "back" (if applicable)
        - Intercardinals: "front right", "front left", etc.
- **Update `parse_compass_direction` function**:
    - Rename to `parse_direction`.
    - Update `CARDINAL_VECTORS` or logic to support "front", "back", "left", "right".
        - front: (0, 1)
        - back: (0, -1)
        - left: (1, 0)
        - right: (-1, 0)
- **Update `NATURAL_MAPPINGS`**:
    - Ensure `pitch` uses "up" and "down" (already present).
    - Ensure `roll` uses "left" and "right" (already present).

### 2. Update Application Logic (`conversation_app/app.py`)
Reflect the changes in how the user message is constructed.

#### [MODIFY] [app.py](file:///home/thor/git/autonomous-intelligence/reachy-mini/conversation_app/app.py)
- **Update `on_speech_stopped`**:
    - Change `doa_compass` variable name to `doa_direction`.
    - Update the user message format:
        - Old: `*Heard from {doa_compass} ({angle_degrees:.1f}°)*`
        - New: `*Heard from speaker at {doa_direction} ({angle_degrees:.1f}°)*`

### 3. Update System Prompt (`conversation_app/agents/reachy/reachy.system.md`)
Update the instructions to the agent.

#### [MODIFY] [reachy.system.md](file:///home/thor/git/autonomous-intelligence/reachy-mini/conversation_app/agents/reachy/reachy.system.md)
- **Update "Movement Directions" section**:
    - Remove references to North, South, East, West.
    - Define directions:
        - **Front** = forward/straight ahead
        - **Right** = to your right
        - **Left** = to your left
        - **Up/Down** = for head nodding/pitch
    - Add instruction about "speaker":
        - "The 'speaker' is the source of the audio you hear."
        - "When you hear from the speaker, turn to face them."

## Verification Plan

### Automated Tests
- Run `python -m conversation_app.tests.test_mappings` (if exists) or create a script to verify `mappings.py` changes.
    - Test `degrees_to_direction(0)` -> "front"
    - Test `degrees_to_direction(90)` -> "right"
    - Test `degrees_to_direction(-90)` -> "left"
    - Test `parse_direction("front right")` -> correct angle.

### Manual Verification
1.  **Start the application**: `python -m conversation_app.app`
2.  **Simulate speech events** (or use actual robot if available):
    - Trigger speech from different angles.
    - Verify the log output shows "Heard from speaker at [direction]".
    - Verify the model response uses natural directions in its reasoning or actions (e.g., `move_antennas`, `set_target_head_pose`).
