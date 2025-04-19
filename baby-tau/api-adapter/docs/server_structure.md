# Server Structure Diagram

The following diagram illustrates how `server.py` connects to its child components in the API Adapter architecture:

```
server.py
├── config.py
│   └── Environment variables & settings
├── models/
│   ├── __init__.py
│   └── requests.py (ResponseRequest model)
├── handlers/
│   ├── __init__.py
│   ├── responses_handler.py
│   │   └── handle_responses()
│   │       ├── message_processor.py
│   │       │   └── process_input_messages()
│   │       ├── utils/conversion_utils.py
│   │       │   ├── convert_to_chat_request()
│   │       │   └── create_basic_response()
│   │       ├── utils/logging_utils.py
│   │       │   ├── generate_request_id()
│   │       │   ├── log_request_details()
│   │       │   └── log_request_response()
│   │       └── stream_processor.py
│   │           └── stream_generator()
│   ├── proxy_handler.py
│   │   └── handle_proxy()
│   │       └── utils/logging_utils.py
│   └── debug_handler.py
│       ├── get_logs()
│       └── get_request_detail()
└── run_server.py (entry point script)
```

## Flow Explanation

1. `server.py` defines the FastAPI application with routes for different endpoints
2. Each route calls a handler function from the `handlers/` directory:
   - `/v1/responses` → `responses_handler.py::handle_responses()`
   - `/{path:path}` → `proxy_handler.py::handle_proxy()`
   - `/debug/*` → `debug_handler.py::get_logs()` or `get_request_detail()`
   
3. The handler functions process requests by:
   - Using models from `models/` directory to validate and parse requests
   - Using utilities from `utils/` directory for common tasks
   - Calling specialized processors like `message_processor.py` and `stream_processor.py`
   
4. All components use configuration from `config.py`

## Key Integration Points

- **Models**: Define data structures used throughout the application
- **Handlers**: Process requests and return responses
- **Utils**: Provide common functionality used by handlers
- **Processors**: Handle specific aspects of request/response processing
- **Config**: Provides global settings and environment variables

## Request Processing Flow

1. Client makes request to API adapter
2. `server.py` routes the request to the appropriate handler
3. Handler processes the request using various utilities and processors
4. Handler returns response to client

This architecture allows for separation of concerns while maintaining a clear flow of data through the system.