# Plan: Numbers to Names Abstraction

## Goal
Abstract away all numerical values from the LLM's perspective. The model should only use descriptive names for robot state and actions. The system will translate these names to numbers for execution and translate numbers back to names for state injection.

## 1. Mappings Definition

We will define a central configuration in `conversation_app/mappings.py` for these mappings.

### Head Pitch (Nodding/Vertical)
| Name | Value (Degrees) | Description |
|------|-----------------|-------------|
| `up` | 20.0 | Looking up |
| `down` | -20.0 | Looking down |
| `slight_up` | 10.0 | Slightly looking up |
| `slight_down` | -10.0 | Slightly looking down |
| `neutral` | 0.0 | Looking straight ahead |

### Head Roll (Tilting)
| Name | Value (Degrees) | Description |
|------|-----------------|-------------|
| `left` | 20.0 | Tilted to the left |
| `right` | -20.0 | Tilted to the right |
| `slight_left` | 10.0 | Slightly tilted left |
| `slight_right` | -10.0 | Slightly tilted right |
| `neutral` | 0.0 | Head upright |

### Head Yaw & Body Yaw (Rotation)
We will continue to use Compass Directions, but ensure they are the **only** accepted input for yaw.
- `North` (0°)
- `North North East` (-22.5°)
- `North East` (-45°)
- `North East East` (-67.5°)
- `East` (-90°)
- `South East East` (-112.5°)
- `South East` (-135°)
- `South South East` (-157.5°)
- `South` (180°)
- `South South West` (157.5°)
- `South West` (135°)
- `South West West` (112.5°)
- `West` (90°)
- `North West West` (67.5°)
- `North West` (45°)
- `North North West` (22.5°)


*Note: Reachy's physical limits will still apply (clamped to ±45° for head, etc.), but the LLM can use these absolute directions.*

### Antennas
| Name | Value (Degrees [Right, Left]) | Description |
|------|-------------------------------|-------------|
| `happy` | [30.0, 30.0] | Both up |
| `sad` | [-30.0, -30.0] | Both down |
| `curious` | [45.0, 45.0] | Perked up high |
| `confused` | [45.0, -45.0] | Asymmetric (Right up, Left down) |
| `alert` | [15.0, 15.0] | Slightly up |
| `neutral` | [0.0, 0.0] | Resting position |

### Duration (Speed)
| Name | Value (Seconds) | Description |
|------|-----------------|-------------|
| `instant` | 0.5 | Very fast |
| `fast` | 1.0 | Fast movement |
| `normal` | 2.0 | Natural pace |
| `slow` | 4.0 | Deliberate/Slow |
| `very_slow` | 6.0 | Very slow |

## 2. Implementation Changes

### A. Create `conversation_app/mappings.py`
1.  **Define Mappings**: Create the `NATURAL_MAPPINGS` dictionary and helper functions (like `get_closest_match`) in this file.
2.  **Move Compass Logic**: Move the compass direction parsing and conversion logic here as well to be shared.

### B. `conversation_app/reachy_controller.py`
1.  **Import Mappings**: Import `NATURAL_MAPPINGS` and helper functions from `mappings.py`.
2.  **Update `get_current_state_natural()`**:
    - Use the shared mappings to find the closest matching name for the current numerical values.
    - Return a dictionary of names: `{ "pitch": "neutral", "roll": "slight_left", "yaw": "North", ... }`.

### C. `conversation_app/action_handler.py`
1.  **Import Mappings**: Import `NATURAL_MAPPINGS` from `mappings.py`.
2.  **Update `_normalize_parameters()`**:
    - Expand this method to handle ALL parameters (`pitch`, `roll`, `yaw`, `body_yaw`, `antennas`, `duration`).
    - It should look up the string value in `NATURAL_MAPPINGS` and replace it with the numerical value.
    - Handle cases where the LLM might still hallucinate a number (try to cast to float as fallback, or strict mode).
3.  **Update State Injection**:
    - Ensure the prompt receives the fully "named" state from `get_current_state_natural()`.

### D. `conversation_app/agents/action-handler/action-handler.system.md`
1.  **Rewrite Prompt**:
    - Remove all references to degrees and seconds.
    - Explicitly list the allowed **Names** for each parameter.
    - Update all examples to use names (e.g., `duration: "fast"`, `pitch: "up"`).
    - Add instruction: "Do NOT use numbers. Use only the provided names."

## 3. Verification Plan
1.  **Unit/Manual Test**:
    - Create a script that simulates an LLM response with names (e.g., `{"tool_name": "move_smoothly_to", "parameters": {"pitch": "up", "duration": "fast"}}`).
    - Verify that `ActionHandler` correctly translates this to `pitch=20.0, duration=1.0`.
    - Verify that `get_current_state_natural()` returns "up" when pitch is ~20.0.
