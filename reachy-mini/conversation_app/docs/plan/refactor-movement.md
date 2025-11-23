# Refactor Movement Actions

Refactor `ActionHandler` to use `ReachyGateway`'s movement methods (`move_to`, `move_smoothly_to`, `move_cyclically`) directly, replacing the existing `operate_robot` pattern and `actions_queue` scripts for these operations.

## User Review Required

> [!IMPORTANT]
> This change replaces the `operate_robot` tool with direct movement tools (`move_to`, `move_smoothly_to`, `move_cyclically`). The LLM will now output these actions directly.
> The `operate_robot` tool and its associated scripts (nod_head, shake_head, etc.) will be deprecated in the prompt, though the scripts remain in the codebase for now.

## Proposed Changes

### Conversation App

#### [MODIFY] [app.py](file:///home/thor/git/autonomous-intelligence/reachy-mini/conversation_app/app.py)
- Update `ActionHandler` initialization to pass `self.gateway`.

#### [MODIFY] [action_handler.py](file:///home/thor/git/autonomous-intelligence/reachy-mini/conversation_app/action_handler.py)
- Update `__init__` to accept `gateway` instance.
- Update `_build_tools_context` to include `move_to`, `move_smoothly_to`, `move_cyclically` definitions (hardcoded or dynamically added).
- Update `execute` to:
    - Check if the action is one of the new movement methods.
    - If so, execute it directly using `await asyncio.to_thread(self.gateway.<method>, ...)` to avoid blocking the event loop.
    - Fallback to `actions_queue` for other actions.
- Update `_parse_action_with_llm` if necessary to support the new tool structure (likely compatible if we keep the `commands` list format or switch to standard tool calls).

#### [MODIFY] [agents/action-handler/action-handler.system.md](file:///home/thor/git/autonomous-intelligence/reachy-mini/conversation_app/agents/action-handler/action-handler.system.md)
- Remove `operate_robot` tool definition.
- Add definitions for:
    - `move_to`
    - `move_smoothly_to`
    - `move_cyclically`
- Add examples of how to use these tools to achieve common behaviors (nodding, shaking head, etc.).

## Verification Plan

### Automated Tests
- Create a test script `conversation_app/tests/test_action_handler_movement.py` that:
    - Mocks `ReachyGateway`.
    - Instantiates `ActionHandler` with the mock gateway.
    - Simulates LLM parsing (or mocks `_parse_action_with_llm`) returning the new movement commands.
    - Verifies that `gateway` methods are called with correct parameters.
    - Verifies that execution is non-blocking (async).

### Manual Verification
- Run `python conversation_app/app.py` (requires robot or mock).
- Speak to the robot (or simulate speech event) asking it to "nod" or "look left".
- Verify logs show `ActionHandler` executing `move_cyclically` or `move_to`.
- Verify robot moves (if connected) or logs indicate movement.
