# message_processor.py Documentation

## Overview

`message_processor.py` is responsible for processing input messages from the client before they are sent to the LLM API. It handles the conversion and formatting of messages between different API formats.

## Key Components

### process_input_messages Function

This is the main function in the file, which:

1. Takes input from a list of message objects
2. Processes and formats the input into messages compatible with the Chat Completions API
3. Handles different input formats (text, messages, function calls, etc.)
4. Returns the processed messages in a standardized format

```python
def process_input_messages(input_list, request_id):
    """
    Process input messages to standardized format.
    
    Args:
        input_list: List of input messages in various formats
        request_id: The unique request ID for logging
        
    Returns:
        A list of messages in the format expected by Chat Completions API
    """
```

### Message Format Conversion

The function handles different input formats:

1. **Regular Messages**: Converting standard user/assistant messages
2. **Function Call Outputs**: Processing function return values and errors
3. **Content Blocks**: Converting content blocks to messages
4. **Image Messages**: Processing image URLs and details
5. **Tool/Function Calls**: Handling function call requests

### Function Call Output Handling

The function has specialized handling for function call outputs:

1. **Error Detection**: Identifies and properly formats function call error messages
2. **Missing Function Names**: Provides default name for missing function name fields
3. **Invalid Arguments**: Enhanced handling of 'invalid arguments: undefined' errors
4. **Follow-up Messages**: Adds follow-up user messages to prompt model responses
5. **Role Assignment**: Ensures proper role assignment for function outputs

### Role Mapping

The function maps between different role naming conventions that might exist between API formats:

- User roles (e.g., "user", "human")
- Assistant roles (e.g., "assistant", "ai")
- System roles (e.g., "system", "instruction")
- Function roles (e.g., "function", "tool")

### Content Processing

The function processes message content to ensure compatibility:

1. Extracting text content from structured message formats
2. Handling attachments or special content types if present
3. Ensuring proper formatting of content for the target API
4. Converting various input formats to a consistent structure

## Integration Points

- Called by the `handle_responses` function in `handlers/responses_handler.py`
- Used during the request conversion process
- Uses logging utilities from the config module

## When to Modify

Modify this file when:

1. Adding support for new message formats
2. Enhancing message processing logic
3. Supporting new message roles or types
4. Improving compatibility between different API formats
5. Adding special handling for certain message content types
6. Improving error handling for function calls

## Best Practices

When working with message processing:

1. Validate input message format before processing
2. Handle edge cases gracefully (empty messages, missing fields)
3. Preserve all relevant message metadata during conversion
4. Log any conversion issues for debugging
5. Ensure backward compatibility with existing message formats
6. Provide descriptive error messages when handling function call errors
7. Always ensure function calls have a usable function name