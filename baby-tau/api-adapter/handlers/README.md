# Handlers Directory

## Overview

The `handlers` directory contains specialized handler functions for different API endpoints in the adapter. These handlers process incoming requests, perform any necessary format conversions, forward the requests to the backend LLM API, and process the responses.

## Directory Structure

```
handlers/
├── __init__.py             # Exports handler functions
├── debug_handler.py        # Debug endpoint handlers
├── proxy_handler.py        # API proxy handler
└── responses_handler.py    # Responses API endpoint handlers
```

## Handler Components

### responses_handler.py

This file contains the handler for the `/v1/responses` endpoint. Its main function is `handle_responses()`, which:

1. Processes requests in the Responses API format
2. Converts them to Chat Completions API format if needed
3. Forwards requests to the LLM API
4. Processes the response, converting it back to Responses format
5. Handles both streaming and non-streaming responses

**When to add to this file**: Add code here when you need to modify how Responses API requests are processed or when you need to enhance the conversion between Response and ChatCompletion formats.

### proxy_handler.py

This file contains the handler for proxying requests to the backend API. Its main function is `handle_proxy()`, which:

1. Takes any request that doesn't match other defined routes
2. Forwards it to the backend LLM API without format conversion
3. Returns the response from the LLM API directly to the client

**When to add to this file**: Add code here when you need to modify how proxy requests are forwarded to the backend API or when you need to add monitoring/logging for proxied requests.

### debug_handler.py

This file contains handlers for debugging endpoints. Its main functions are:

1. `get_logs()`: Returns recent request/response logs for debugging
2. `get_request_detail()`: Returns detailed information about a specific request

**When to add to this file**: Add code here when you need to enhance debugging capabilities or add new monitoring endpoints.

## Integration Points

The handlers are imported in `__init__.py` and used by the main FastAPI application in `server.py`. They use utility functions from the `utils` directory and models from the `models` directory.

## Common Patterns

All handlers follow a similar pattern:

1. Receive a request
2. Generate a unique request ID
3. Log request details
4. Process the request
5. Log the response
6. Return the response to the client

## Error Handling

Handlers use FastAPI's `HTTPException` for error handling. Common error scenarios:

- Connection errors to the backend API (503)
- Request timeouts (504)
- Backend API errors (forwarded status code)
- Internal server errors (500)