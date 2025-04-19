# stream_processor.py Documentation

## Overview

`stream_processor.py` handles the processing and conversion of streaming responses from the LLM API. It's responsible for taking streaming events from the backend API and converting them to the appropriate format for the client.

## Key Components

### stream_generator Function

This is the main function in the file, which:

1. Takes a streaming response from the LLM API
2. Processes each chunk of data as it arrives
3. Converts the data to the appropriate format (either Responses or Chat Completions)
4. Yields the formatted data for the client

```python
async def stream_generator(
    response, 
    model_name, 
    request_id, 
    store=False, 
    temperature=1.0, 
    top_p=1.0
):
    """
    Generate streaming events from the LLM API response.
    
    Args:
        response: The streaming response from the backend API
        model_name: The name of the model being used
        request_id: The unique request ID
        store: Whether to store the response
        temperature: The temperature parameter value
        top_p: The top_p parameter value
        
    Yields:
        Formatted SSE events in the appropriate format
    """
```

### Format Conversion

The function handles the different streaming formats:

1. **Chat Completions Format**: Processing chunks in the Chat Completions streaming format
2. **Responses Format**: Converting to the Responses streaming format
3. **Special Event Types**: Handling special event types like completion and error events

### Function Call Handling

The function has specialized handling for function/tool calls:

1. **Multiple Tool Call Formats**: Supports both traditional `function_call` and newer `tool_calls` formats
2. **Argument Streaming**: Properly handles streaming of function arguments as they arrive
3. **Completion Detection**: Uses finish_reason to detect when tool calls are complete
4. **Error Handling**: Special handling for invalid arguments and error cases
5. **Reliable Done Events**: Ensures done events are always emitted for every function call

Function call events follow this sequence:
1. `response.function_call` - Indicates a function call with a name
2. `response.function_call_arguments.delta` - Streams function arguments as they arrive
3. `response.function_call_arguments.done` - Signals function arguments are complete

### Event Types

The function processes several types of streaming events:

- `response.created`: Initial event indicating a response has been created
- `response.in_progress`: Ongoing event with partial content
- `response.completed`: Final event indicating completion
- `response.error`: Error event if something goes wrong
- `response.content_block_delta`: Event with partial content
- `response.function_call`: Event indicating a function call
- `response.function_call_arguments.delta`: Event with partial function arguments
- `response.function_call_arguments.done`: Event indicating function arguments are complete

### SSE Formatting

The function formats the data as Server-Sent Events (SSE) for streaming to the client:

```
data: {"type": "response.created", ... }

data: {"type": "response.in_progress", ... }

data: {"type": "response.completed", ... }
```

## Integration Points

- Called by the `handle_responses` function in `handlers/responses_handler.py`
- Uses utilities from the `utils` directory for format conversion
- Uses configuration from `config.py`

## When to Modify

Modify this file when:

1. Adding support for new streaming formats
2. Enhancing conversion between streaming formats
3. Improving error handling in streaming responses
4. Optimizing streaming performance
5. Adding additional event types or fields to streaming responses
6. Fixing issues with function call handling

## Best Practices

When working with streaming responses:

1. Handle errors gracefully to prevent stream interruptions
2. Format SSE events correctly with the required format
3. Ensure proper encoding of special characters in JSON
4. Properly close the stream when complete
5. Include appropriate headers for SSE compatibility
6. Always emit `done` events for function calls, even in error cases
7. Handle both standard and tool-based function call formats