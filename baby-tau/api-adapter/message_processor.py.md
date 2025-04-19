# message_processor.py Documentation

## Overview

`message_processor.py` is responsible for processing input messages from the client before they are sent to the LLM API. It handles the conversion and formatting of messages between different API formats.

## Key Components

### process_input_messages Function

This is the main function in the file, which:

1. Takes input from a ResponseRequest object
2. Processes and formats the input into messages compatible with the Chat Completions API
3. Handles different input formats (text, messages, etc.)
4. Returns the processed messages in a standardized format

```python
def process_input_messages(request: ResponseRequest):
    """
    Process input from a ResponseRequest and convert to chat messages format.
    
    Args:
        request: The ResponseRequest object containing the input
        
    Returns:
        A list of messages in the format expected by Chat Completions API
    """
```

### Message Format Conversion

The function handles different input formats:

1. **Text Input**: Converting simple text input to a user message
2. **Message Array**: Processing an array of messages with roles and content
3. **Special Formats**: Handling any special message formats or instructions

### Role Mapping

The function maps between different role naming conventions that might exist between API formats:

- User roles (e.g., "user", "human")
- Assistant roles (e.g., "assistant", "ai")
- System roles (e.g., "system", "instruction")

### Content Processing

The function processes message content to ensure compatibility:

1. Extracting text content from structured message formats
2. Handling attachments or special content types if present
3. Ensuring proper formatting of content for the target API

## Integration Points

- Called by the `handle_responses` function in `response_handler.py`
- Used during the request conversion process
- May use utilities from the `utils` directory

## When to Modify

Modify this file when:

1. Adding support for new message formats
2. Enhancing message processing logic
3. Supporting new message roles or types
4. Improving compatibility between different API formats
5. Adding special handling for certain message content types

## Best Practices

When working with message processing:

1. Validate input message format before processing
2. Handle edge cases gracefully (empty messages, missing fields)
3. Preserve all relevant message metadata during conversion
4. Log any conversion issues for debugging
5. Ensure backward compatibility with existing message formats