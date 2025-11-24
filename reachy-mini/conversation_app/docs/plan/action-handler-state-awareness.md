# Action Handler State Awareness Plan

## Goal
Enable the `ActionHandler` to be aware of the robot's current physical state (head pose, antennas, body yaw) so that the LLM can make context-aware decisions (e.g., "look back" implies knowing where it is currently looking).

## Implemented Changes

### Conversation App

#### [MODIFY] [gateway.py](file:///home/thor/git/autonomous-intelligence/reachy-mini/conversation_app/gateway.py)
- Added `get_current_state()` method to `ReachyGateway` class.
- This method delegates to `self.reachy_controller._get_current_state()`.
- **FIXED**: Updated `move_to`, `move_smoothly_to`, and `move_cyclically` wrapper methods to use correct parameter names (`roll`, `pitch`, `yaw`, `antennas`, `body_yaw`) instead of incorrectly prefixed names (`head_roll`, `head_pitch`, `head_yaw`).
- **FIXED**: Changed default values from `0.0` to `None` to support patch movement (maintaining current position when parameter not specified).

#### [MODIFY] [action_handler.py](file:///home/thor/git/autonomous-intelligence/reachy-mini/conversation_app/action_handler.py)
- In `_parse_action_with_llm`, retrieved the current state from `self.gateway`.
- Formatted the state as a readable string (e.g., `Current State: roll=..., pitch=..., ...`).
- Appended this state information to the `user_message` (as required for vLLM prefix caching - system message must remain static).

#### [MODIFY] [action-handler.system.md](file:///home/thor/git/autonomous-intelligence/reachy-mini/conversation_app/agents/action-handler/action-handler.system.md)
- Updated the system prompt to inform the agent that it will receive the "Current State" of the robot.
- Instructed the agent to use this state for relative movements or context-aware actions.
- **FIXED**: Corrected all parameter names from `head_yaw`, `head_pitch`, `head_roll` to `yaw`, `pitch`, `roll` throughout the entire system prompt, including:
  - Parameter descriptions for `move_to`, `move_smoothly_to`, and `move_cyclically`
  - All example JSON responses (nodding, shaking head, tilting head, looking around, response format)

## Verification
- ✅ The changes have been applied to the codebase.
- ✅ The `ActionHandler` now has access to the robot's state via the `gateway` instance.
- ✅ The LLM prompt will now include the current state, allowing for more intelligent action generation.
- ✅ **CRITICAL FIX**: Parameter names are now consistent across the entire stack (system prompt → LLM output → gateway methods → reachy_controller methods).
- ⚠️ **Manual Testing Required**: The system should be tested to verify that state-aware movements work correctly (e.g., asking the robot to "look back" or "nod" should use the current state as reference).
