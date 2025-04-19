# response_handler.py Documentation

## Overview

`response_handler.py` is responsible for handling requests to the Responses API endpoint. It processes incoming requests, converts them to the appropriate format, forwards them to the LLM API, and processes the responses.

## Key Components

### handle_responses Function

This is the main function in the file, which:

1. Takes a `ResponseRequest` object and a raw FastAPI `Request` object
2. Generates a unique request ID
3. Logs request details
4. Processes the request based on the input format
5. Converts the request to Chat Completions format if needed
6. Sends the request to the LLM API
7. Handles streaming vs non-streaming responses
8. Logs the response
9. Returns the response to the client

```python
async def handle_responses(request: ResponseRequest, raw_request: Request):
    """
    Handle requests to the Responses API endpoint.
    
    Args:
        request: The parsed ResponseRequest object
        raw_request: The raw FastAPI Request object
        
    Returns:
        Either a StreamingResponse or a JSON response depending on the request
    """
```

### Request Processing

The function processes requests by:

1. Generating a request ID with `generate_request_id()`
2. Processing input messages with `process_input_messages()`
3. Converting to chat format with `convert_to_chat_request()`
4. Making the API request with httpx client
5. Processing the response

### Streaming Response Handling

For streaming requests, the function:

1. Returns a FastAPI `StreamingResponse`
2. Uses `stream_generator()` to convert streaming events on the fly
3. Sets appropriate headers for SSE (Server-Sent Events)

### Non-Streaming Response Handling

For non-streaming requests, the function:

1. Parses the JSON response
2. Creates a basic response structure
3. Returns a regular JSON response

## Error Handling

The function handles several error scenarios:

- Timeouts (504 status code)
- Connection errors (503 status code)
- HTTP errors (502 status code)
- LLM API errors (forwarded status code)
- Internal errors (500 status code)

## Integration Points

- Uses utility functions from the `utils` directory
- Uses models from the `models` directory
- Uses configuration from `config.py`
- Called by route handlers in `server.py`

## When to Modify

Modify this file when:

1. Adding support for new Responses API features
2. Enhancing the conversion logic between Responses and Chat formats
3. Improving error handling and logging
4. Optimizing request processing performance