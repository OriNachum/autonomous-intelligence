# Audit Logging Implementation Plan

## Goal
Implement a comprehensive audit logging system to track the entire lifecycle of a conversation turn, from audio recording to robot action completion. This will enable debugging, performance analysis, and conversation review.

## Architecture
We will introduce a `ConversationLogger` class in `conversation_app/logger.py`. This class will be responsible for writing structured logs (JSONL format) to a daily log file (e.g., `logs/conversation_audit_YYYY-MM-DD.jsonl`).

The logger will support different event types corresponding to the user's requirements.

## Log Event Structure
Each log entry will have at least:
```json
{
  "timestamp": "ISO-8601 string",
  "event_type": "string",
  "event_id": "uuid (optional, to correlate related events)",
  "data": { ... }
}
```

## Proposed Changes

### 1. Create `conversation_app/logger.py` [NEW]
- Define `ConversationLogger` class.
- Methods for each specific log event to ensure consistent schema.
- Singleton pattern or shared instance management.

### 2. Modify `conversation_app/gateway.py`
- Integrate `ConversationLogger`.
- Log:
    - `speech_recording_started`: When recording starts.
    - `speech_recording_finished`: When recording stops (duration, size).
    - `transcription_started`: Before calling Whisper.
    - `transcription_finished`: After Whisper returns (text, duration).

### 3. Modify `conversation_app/app.py`
- Integrate `ConversationLogger`.
- Log:
    - `model_request_sent`: Input messages, parameters.
    - `model_response_chunk`: Stream chunks (optional, maybe too verbose? User asked for "responses from the model"). We might log the aggregated response at the end or significant chunks.
    - `model_response_finished`: Full response text.
    - `parsing_finished`: For each cut (stream mode).

### 4. Modify `conversation_app/whisper_stt.py`
- (Optional) If `gateway.py` covers it, we might not need changes here, but `gateway.py` calls `transcribe_audio_data`. Logging inside `whisper_stt.py` might be more precise for timing. Let's stick to `gateway.py` for now as it orchestrates it.

### 5. Modify `conversation_app/tts_queue.py`
- Integrate `ConversationLogger`.
- Log:
    - `tts_request_queued`: Text added to queue.
    - `tts_started`: Playback starts.
    - `tts_finished`: Playback finishes.

### 6. Modify `conversation_app/action_handler.py`
- Integrate `ConversationLogger`.
- Log:
    - `action_sent_to_handler`: When `execute` is called.
    - `action_parsing_started`: Before LLM parsing.
    - `action_parsing_finished`: After LLM parsing (commands).
    - `command_execution_started`: For each command.
    - `command_execution_finished`: For each command.
    - `action_handler_finished`: When `execute` completes.
    - **State Logging**: Log full input and state before and after commands are sent to the model (in `_parse_action_with_llm`).

### 7. Modify `conversation_app/actions_queue.py`
- Integrate `ConversationLogger`.
- Log:
    - `action_queued`: When added to queue.
    - `action_execution_started`: When worker picks it up.
    - `action_execution_finished`: When worker finishes.

## Detailed Event List & Fields

| Event Type | Source | Fields |
|------------|--------|--------|
| `speech_recording_started` | Gateway | `event_number` |
| `speech_recording_finished` | Gateway | `event_number`, `duration`, `samples` |
| `transcription_started` | Gateway | `event_number` |
| `transcription_finished` | Gateway | `event_number`, `text`, `latency_ms` |
| `model_request_sent` | App | `messages`, `parameters` |
| `model_response_started` | App | - |
| `model_response_finished` | App | `full_text`, `latency_ms` |
| `parser_cut` | App | `type` (speech/action), `content` |
| `tts_request_queued` | App/SpeechHandler | `text` |
| `tts_started` | TTSQueue | `text`, `audio_file` |
| `tts_finished` | TTSQueue | `text`, `duration_ms` |
| `action_received` | ActionHandler | `action_string` |
| `action_llm_request` | ActionHandler | `prompt`, `current_state` |
| `action_llm_response` | ActionHandler | `response`, `parsed_commands` |
| `command_started` | ActionHandler | `command`, `parameters`, `state_before` |
| `command_finished` | ActionHandler | `command`, `state_after` |

## Verification Plan

### Automated Tests
- Create a test script `tests/test_audit_logging.py` that:
    1. Instantiates the logger.
    2. Simulates a sequence of events.
    3. Verifies the log file is created and contains valid JSONL with expected fields.

### Manual Verification
1. Run the conversation app.
2. Speak to the robot ("Hello").
3. Wait for response and movement.
4. Check the generated log file (e.g., `logs/audit.jsonl`).
5. Verify all events from the list above are present and chronologically correct.
