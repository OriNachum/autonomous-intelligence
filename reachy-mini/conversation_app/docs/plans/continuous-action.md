# Continuous Action & Self-Reaction Plan

## Goal
Implement a unified queueing system where both speech and physical actions are processed sequentially, and their execution status is back-propagated to the conversation model to enable self-reaction.

## Current State
- **Speech**: Handled directly by `app.py` via `speech_handler` (immediate execution).
- **Actions**: Handled by `action_handler` -> `actions_queue` (background execution).
- **Synchronization**: Loose synchronization; speech can overlap with actions or happen out of order if not carefully managed.
- **Feedback**: No feedback to the model about action completion or failure.

## Proposed Changes

### 1. Unified Action Queue
Treat speech as an action to ensure strict ordering and synchronization with movements.

#### [NEW] `conversation_app/actions/speak.json`
Define a `speak` tool that takes `text` as a parameter.

#### [NEW] `conversation_app/actions/scripts/speak.py`
Implement the `speak` action script that uses `tts_queue` to synthesize speech.

#### [MODIFY] `conversation_app/app.py`
- Modify `process_message` to:
    - Capture text content from the LLM response.
    - Instead of calling `speech_handler.speak()` directly, create a `speak` tool call.
    - Enqueue the `speak` tool call to `action_handler` along with other tool calls.
    - Ensure tool calls are enqueued in the order they appear (or speech first/last as appropriate).

### 2. Execution Feedback Loop
Enable `actions_queue` to report execution status back to the application.

#### [MODIFY] `conversation_app/actions_queue.py`
- Add `event_callback` parameter to `__init__`.
- In `_execute_action`, call `event_callback` with status updates:
    - `action_started`: When execution begins.
    - `action_completed`: When execution succeeds.
    - `action_failed`: When execution fails (with error message).

#### [MODIFY] `conversation_app/action_handler.py`
- Update `__init__` to accept `event_callback`.
- Pass `event_callback` to `AsyncActionsQueue`.

### 3. Model Context Update (Back-Propagation)
Update the conversation history with action execution results so the model "knows" what happened.

#### [MODIFY] `conversation_app/app.py`
- Implement `on_action_event` callback.
- When `action_completed` or `action_failed` event is received:
    - Format a system message (e.g., `[System] Action 'nod_head' completed successfully.`).
    - Append this message to `self.messages`.
    - (Optional) Trigger a model run if "self-reaction" is desired immediately (though usually, this just informs the *next* turn).

## Verification Plan

### Automated Tests
1.  **Unit Test for Speak Action**:
    - Create `tests/test_speak_action.py`.
    - Verify `speak.py` correctly enqueues text to `tts_queue`.
2.  **Integration Test for Feedback Loop**:
    - Create `tests/test_action_feedback.py`.
    - Mock `event_callback`.
    - Enqueue an action.
    - Verify callback is called with `started` and `completed` events.

### Manual Verification
1.  **Speech via Action**:
    - Run the app.
    - Speak to the robot: "Say hello."
    - Verify "hello" is spoken via the `speak` action (check logs for `Executing action: speak`).
2.  **Action Sequence**:
    - Speak: "Nod your head and say yes."
    - Verify robot nods, then says "yes" (or vice versa, depending on order).
    - Verify logs show sequential execution.
3.  **Self-Reaction**:
    - Speak: "Wobble your head."
    - Wait for wobble to finish.
    - Speak: "What did you just do?"
    - Verify robot answers "I just wobbled my head" (or similar, indicating it knows the action succeeded).
