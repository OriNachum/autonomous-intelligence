# Conversation App Package

A refactored conversation application with speech event integration for the Reachy robot.

## Structure

The conversation app has been refactored into a modular package with the following components:

```
conversation_app/
├── __init__.py              # Package initialization and exports
├── app.py                   # Main ConversationApp class
├── event_handler.py         # EventHandler for speech events
└── conversation_parser.py   # ConversationParser for response parsing
```

## Components

### EventHandler (`event_handler.py`)

Handles speech events from the hearing_event_emitter service via Unix Domain Socket.

**Key Features:**
- Unix Domain Socket connection management
- Event listening and parsing
- Speech started/stopped event handling
- Callback-based event notification
- Automatic reconnection with retry logic

**Usage:**
```python
from conversation_app import EventHandler

async def on_speech_stopped(data):
    print(f"Speech stopped: {data}")

handler = EventHandler()
handler.set_speech_stopped_callback(on_speech_stopped)
await handler.connect()
await handler.listen()
```

### ConversationParser (`conversation_parser.py`)

Parses conversation responses from the LLM to extract speech and actions.

**Key Features:**
- Token-by-token parsing for streaming responses
- Extracts speech content (text in quotes "...")
- Extracts action content (text in **...**)
- Maintains separate queues for speech and actions
- Stateful parser that handles partial tokens

**Usage:**
```python
from conversation_app import ConversationParser

parser = ConversationParser()
parser.reset()

# Parse tokens from streaming response
for token in response_stream:
    parser.parse_token(token)

# Access parsed content
while parser.has_speech():
    speech = parser.get_speech()
    print(f"Speech: {speech}")

while parser.has_action():
    action = parser.get_action()
    print(f"Action: {action}")
```

### ConversationApp (`app.py`)

Main application class that orchestrates the conversation flow.

**Key Features:**
- Integrates EventHandler and ConversationParser
- Manages conversation history
- Handles vLLM streaming chat completions
- Processes speech events through the LLM
- Queues parsed speech and actions for execution

**Usage:**
```python
from conversation_app import ConversationApp

app = ConversationApp()
await app.initialize()
await app.run()
```

## Running the Application

### From the root directory:
```bash
python conversation_app.py
```

### As a module:
```bash
python -m conversation_app.app
```

### Import and use programmatically:
```python
import asyncio
from conversation_app import ConversationApp

async def main():
    app = ConversationApp()
    await app.initialize()
    await app.run()

asyncio.run(main())
```

## Requirements

- Hearing event emitter running (`hearing_event_emitter.py`)
- vLLM server running on http://localhost:8100 with streaming support
- System prompt at `agents/reachy/reachy.system.md`

## Configuration

Environment variables:
- `SOCKET_PATH`: Path to Unix Domain Socket (default: `/tmp/reachy_sockets/hearing.sock`)

## Output Format

The parser extracts two types of content from LLM responses:

1. **Speech** (text in quotes): `"Hello, how are you?"`
   - Added to speech queue for TTS processing
   
2. **Actions** (text in double asterisks): `**nod_head**`
   - Added to action queue for robot movement

## Benefits of Refactoring

1. **Separation of Concerns**: Event handling, parsing, and conversation logic are now separate modules
2. **Reusability**: Each component can be used independently
3. **Testability**: Easier to unit test individual components
4. **Maintainability**: Cleaner code structure with focused responsibilities
5. **Extensibility**: Easy to add new event types or parsing rules
6. **Backward Compatibility**: Original `conversation_app.py` entry point still works

## Migration Guide

If you were importing from the old `conversation_app.py`:

**Before:**
```python
from conversation_app import ConversationApp
```

**After:**
```python
# Still works! (backward compatible)
from conversation_app import ConversationApp

# Or use the new package directly
from conversation_app.app import ConversationApp
from conversation_app import EventHandler, ConversationParser
```

## Development

To extend the functionality:

1. **Add new event types**: Modify `EventHandler` to handle new events
2. **Add new parsing rules**: Extend `ConversationParser` with new patterns
3. **Customize conversation flow**: Modify `ConversationApp` callbacks

## Future Enhancements

Potential improvements:
- Add speech transcription integration (Whisper)
- Implement TTS queue processing
- Add action queue executor
- Support multiple socket connections
- Add configuration file support
- Implement conversation state persistence
