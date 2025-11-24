# Action Handler State Awareness Plan

## Goal
Enable the `ActionHandler` to be aware of the robot's current physical state (head pose, antennas, body yaw) so that the LLM can make context-aware decisions (e.g., "look back" implies knowing where it is currently looking).

## Implemented Changes

### Conversation App

#### [MODIFY] [gateway.py](file:///home/thor/git/autonomous-intelligence/reachy-mini/conversation_app/gateway.py)
- Added `get_current_state()` method to `ReachyGateway` class.
- This method delegates to `self.reachy_controller._get_current_state()`.

#### [MODIFY] [action_handler.py](file:///home/thor/git/autonomous-intelligence/reachy-mini/conversation_app/action_handler.py)
- In `_parse_action_with_llm`, retrieved the current state from `self.gateway`.
- Formatted the state as a readable string (e.g., `Current State: roll=..., pitch=..., ...`).
- Appended this state information to the `user_message`.

#### [MODIFY] [action-handler.system.md](file:///home/thor/git/autonomous-intelligence/reachy-mini/conversation_app/agents/action-handler/action-handler.system.md)
- Updated the system prompt to inform the agent that it will receive the "Current State" of the robot.
- Instructed the agent to use this state for relative movements or context-aware actions.

## Verification
- The changes have been applied to the codebase.
- The `ActionHandler` now has access to the robot's state via the `gateway` instance.
- The LLM prompt will now include the current state, allowing for more intelligent action generation.
