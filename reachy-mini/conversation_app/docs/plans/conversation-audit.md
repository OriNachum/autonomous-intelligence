# Conversation Audit Plan

## Goal
Implement a new audit logging mechanism that records the full conversation context for each session.
- **File Format**: `conversation.<timestamp>.log`
- **Scope**: One file per session (initialization).
- **Content**:
    1.  System Prompt (What the system is).
    2.  User Request (Full message content).
    3.  Model Response (Full message content, including tool calls).

## Proposed Changes

### `conversation_app/app.py`

#### `ConversationApp` Class

1.  **`__init__`**:
    -   Initialize `self.audit_log_path = None`.

2.  **`initialize()`**:
    -   Generate a timestamped filename: `conversation.{datetime.now().strftime('%Y%m%d_%H%M%S')}.log`.
    -   Set `self.audit_log_path` to `conversation_app/logs/<filename>`.
    -   Ensure the `conversation_app/logs` directory exists.
    -   Write the **System Prompt** to the new log file.
        -   Header: `--- SYSTEM PROMPT ---`
        -   Content: `self.system_prompt`
        -   Footer: `---------------------`

3.  **`process_message(user_message)`**:
    -   After adding the user message to `self.messages`, append it to the audit log.
        -   Header: `--- USER REQUEST ---`
        -   Content: Full user message object (or structured text representation).
    -   After receiving the full assistant response, append it to the audit log.
        -   Header: `--- MODEL RESPONSE ---`
        -   Content: Full assistant message object (including `tool_calls` if any).

#### Implementation Details
-   Use `json.dumps(msg, indent=2)` for logging message objects to ensure "not just text" is captured in a readable format.
-   Append to the file in real-time to ensure logs are saved even if the app crashes.

## Verification Plan

### Manual Verification
1.  Start the `conversation_app`.
2.  Verify that a new file `conversation_app/logs/conversation.<timestamp>.log` is created.
3.  Check that the file starts with the System Prompt.
4.  Interact with the robot (simulate speech or use the app).
5.  Check that the log file is updated with:
    -   The User Request.
    -   The Model Response (including any tool calls).
6.  Restart the app and verify a *new* file is created.
