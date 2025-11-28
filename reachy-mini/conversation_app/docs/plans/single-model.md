# Single Model Architecture Plan

## Goal
Transition `conversation_app` to a single-model architecture where the "front" model handles both conversation and action generation using function calling (or structured output), eliminating the need for a secondary LLM for action parsing and the `**...**` syntax.

## User Review Required
> [!IMPORTANT]
> This change removes the `**...**` action syntax. The model will now be expected to output structured tool calls.
> The `action_handler.py` will no longer use an LLM to parse actions; it will rely on the structured output from the front model.

## Proposed Changes

### Conversation App
#### [MODIFY] [app.py](file:///home/thor/git/autonomous-intelligence/reachy-mini/conversation_app/app.py)
- Update `process_message` to handle structured tool calls from the model response.
- Remove `**...**` parsing logic from `ConversationParser` usage (or update parser to handle tool calls).
- When a tool call is detected, emit an `action_triggered` event or directly call `self.action_handler.execute()`.
- Update `system_prompt` loading to include tool definitions.

#### [MODIFY] [action_handler.py](file:///home/thor/git/autonomous-intelligence/reachy-mini/conversation_app/action_handler.py)
- Remove `_parse_action_with_llm` method and the secondary LLM client.
- Update `execute` method to accept structured command objects (tool name + parameters) directly.
- Retain parameter resolution logic (e.g., handling "DOA", "return", "back").

#### [MODIFY] [agents/reachy/reachy.system.md](file:///home/thor/git/autonomous-intelligence/reachy-mini/conversation_app/agents/reachy/reachy.system.md)
- Remove instructions regarding `**...**` syntax.
- Add clear definitions and examples for the available tools/actions:
    - `nod_head`
    - `shake_head`
    - `wobble_head`
    - `set_target_head_pose` (head to sides)
- Emphasize using function calling/tools for actions.

### Actions
#### [NEW] [actions/scripts/wobble_head.py](file:///home/thor/git/autonomous-intelligence/reachy-mini/conversation_app/actions/scripts/wobble_head.py)
- Implement `wobble_head` action (circular head movement).

#### [NEW] [actions/scripts/set_target_head_pose.py](file:///home/thor/git/autonomous-intelligence/reachy-mini/conversation_app/actions/scripts/set_target_head_pose.py)
- Implement `set_target_head_pose` action to move head to specific angles (roll, pitch, yaw).

#### [MODIFY] [actions/scripts/nod_head.py](file:///home/thor/git/autonomous-intelligence/reachy-mini/conversation_app/actions/scripts/nod_head.py)
- Ensure compatibility with new calling convention if needed (likely fine as is).

#### [MODIFY] [actions/scripts/shake_head.py](file:///home/thor/git/autonomous-intelligence/reachy-mini/conversation_app/actions/scripts/shake_head.py)
- Ensure compatibility with new calling convention if needed.

## Verification Plan

### Automated Tests
- Create a test script `tests/test_single_model_actions.py` to:
    - Mock the model response with tool calls.
    - Verify `app.py` correctly parses them and calls `action_handler`.
    - Verify `action_handler` executes the corresponding script.

### Manual Verification (Manual)
1.  **Start the app**: `python -m conversation_app.app`
2.  **Speak to Reachy**: "Nod your head."
3.  **Verify**:
    - Log shows "Tool call detected: nod_head".
    - Robot physically nods.
4.  **Speak to Reachy**: "Look to the left." (triggers `set_target_head_pose` or `look_at_direction`).
5.  **Verify**: Robot looks left.
6.  **Speak to Reachy**: "Wobble your head."
7.  **Verify**: Robot performs wobble motion.
