# Utils Directory

## Overview

The `utils` directory contains utility functions organized by their purpose. These utilities provide common functionality used throughout the API adapter for tasks such as logging, format conversion, and streaming response handling.

## Directory Structure

```
utils/
├── __init__.py           # Exports utility functions 
├── conversion_utils.py   # Functions for converting between API formats
├── logging_utils.py      # Logging and request tracking functions
└── streaming.py          # Utilities for handling streaming responses
```

## Utility Components

### conversion_utils.py

This file contains functions for converting between different API formats:

- `process_input_messages()`: Processes input messages for conversion
- `convert_to_chat_request()`: Converts Responses API requests to Chat Completions format
- `create_basic_response()`: Creates a basic response structure in Responses API format

**When to add to this file**: Add code here when implementing new conversion functionality between API formats or enhancing existing conversion logic.

### logging_utils.py

This file contains functions for logging and request tracking:

- `generate_request_id()`: Generates a unique ID for each request
- `log_request_response()`: Logs request and response data
- `log_request_details()`: Logs detailed request information
- `request_logs`: Storage for recent request logs

**When to add to this file**: Add code here when enhancing logging capabilities, adding new request tracking features, or improving debug information.

### streaming.py

This file contains utilities for handling streaming responses:

- `stream_generator()`: Generates streaming response events in the appropriate format

**When to add to this file**: Add code here when enhancing streaming response functionality or supporting new streaming formats.

## Integration Points

The utility functions are imported in `__init__.py` and used throughout the application, especially in the handler functions. They provide core functionality that is reused across different parts of the adapter.

## Common Patterns

Most utility functions follow these patterns:

1. Take structured input parameters
2. Perform a specific, focused task
3. Return a well-defined result
4. Handle errors appropriately
5. Include logging for debugging

## Error Handling

Utility functions should handle errors gracefully and provide clear error messages. When errors occur:

1. Log the error with appropriate context
2. Raise appropriate exceptions when needed
3. Include error details to aid in debugging