# Natural Movement Implementation Plan

## Goal
Enable the robot to be controlled using "cardinal points" (natural language descriptors like "left", "right", "up", "down") instead of raw degree values. This applies to both the input (LLM controlling the robot) and the output (LLM understanding the robot's current state).

## User Review Required
> [!IMPORTANT]
> **Mapping Definitions**: I have defined a set of mappings for cardinal points to degrees. Please review these in the "Proposed Changes" section to ensure they match your expectations of "natural" movement.
>
> **State Representation**: The robot's state will now be presented to the LLM as cardinal points (e.g., "looking left") instead of exact degrees. This is a significant change in how the LLM perceives the robot.

## Proposed Changes

### 1. `conversation_app/reachy_controller.py`

#### [MODIFY] `ReachyController` class
- **Add `parse_compass_direction(direction_str)` helper method**:
    - Implement a vector-addition based parser to handle arbitrary compass strings (e.g., "North North East").
    - **Logic**:
        - Define unit vectors: `North=(0, 1)`, `South=(0, -1)`, `East=(1, 0)`, `West=(-1, 0)`.
        - Tokenize the input string (e.g., "NorthEast" -> ["North", "East"]).
        - Sum the vectors.
        - Calculate the angle of the resulting vector relative to North.
        - **Mapping to Reachy Yaw**:
            - Reachy's yaw is limited to approx ±45°.
            - Map Compass 90° (East) to Reachy -45° (Max Right).
            - Map Compass -90° (West) to Reachy +45° (Max Left).
            - Formula: `reachy_yaw = -1 * (compass_angle / 2)`
            - Clamp result to safety limits.
- **Update `NATURAL_MAPPINGS`**:
    - Keep `pitch`, `roll`, `antennas` as explicit mappings.
    - Remove `yaw` and `body_yaw` explicit mappings in favor of the parser.
- **Update `move_to`, `move_smoothly_to`, `move_cyclically`**:
    - If `yaw` or `body_yaw` is a string:
        - Call `parse_compass_direction`.
        - Use the result as the target degree.
- **Update `_get_current_state`**:
    - Add `get_current_state_natural()`:
        - Convert current yaw back to a compass string (e.g., if yaw is -45, return "East").
        - Use simple quantization for return values (North, NE, E, SE, S, SW, W, NW).

### 2. `conversation_app/action_handler.py`

#### [MODIFY] `ActionHandler` class
- **Update `_build_tools_context`**:
    - Update `yaw` and `body_yaw` parameter descriptions to include "Compass directions (e.g., 'North', 'North East', 'West')".
- **Update `_parse_action_with_llm`**:
    - Inject state using compass directions.

### 3. System Prompts

#### [MODIFY] `conversation_app/agents/action-handler/action-handler.system.md`
- Update examples to use compass directions.
  - Example: `{"tool_name": "move_to", "parameters": {"yaw": "North East"}}`

#### [MODIFY] `conversation_app/agents/reachy/reachy.system.md`
- Mention that the robot understands compass directions relative to its "North" (forward).

## Verification Plan

### Automated Tests
- **Unit Test for Compass Parser**:
    - Create `test_compass.py`.
    - Test cases:
        - "North" -> 0°
        - "East" -> -45°
        - "West" -> 45°
        - "North East" -> -22.5°
        - "North North East" -> ~-13° (approx)
        - "South" -> Clamp to limit (or 0 if we decide South is invalid, but likely just max turn).
- **Integration Test**:
    - Verify `move_to(yaw="East")` calls `goto_target` with yaw=-45.

### Manual Verification
- **Interactive Test**:
    - Speak: "Look North East".
    - Verify robot turns head slightly right (~22°).
    - Speak: "Look West".
    - Verify robot turns head left (~45°).
