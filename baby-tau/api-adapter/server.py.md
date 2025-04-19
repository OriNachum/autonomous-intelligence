# server.py Documentation

## Overview

`server.py` is the main entry point and FastAPI application that defines all routes and handlers for the API Adapter. It serves as a compatibility layer between different API formats, specifically focusing on translating between the OpenAI Responses API and Chat Completions API.

## Key Components

### FastAPI App Configuration

```python
app = FastAPI(title="API Adapter", description="Adapter between Responses API and Chat Completions API")

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
```

This sets up the FastAPI application with CORS middleware to allow cross-origin requests from any domain, which is essential for clients running in browsers.

### Route Definitions

The server defines several key routes:

1. **Responses API Endpoints**:
   ```python
   @app.post("/v1/responses")
   async def responses(request: ResponseRequest, raw_request: Request):
       """Handle Responses API requests"""
       return await handle_responses(request, raw_request)
   
   @app.post("/responses")
   async def responses_without_prefix(request: ResponseRequest, raw_request: Request):
       """Handle Responses API requests without the /v1/ prefix"""
       return await handle_responses(request, raw_request)
   ```
   
   These endpoints handle requests in the Responses API format, with both the `/v1` prefix version and a non-prefixed version for compatibility.

2. **Debug Endpoints**:
   ```python
   @app.get("/debug/logs")
   async def debug_logs(limit: int = 10, request_id: str = None):
       """Endpoint to view recent request/response logs for debugging"""
       return await get_logs(limit, request_id)

   @app.get("/debug/request/{request_id}")
   async def debug_request_detail(request_id: str):
       """Get detailed information about a specific request by ID"""
       return await get_request_detail(request_id)
   ```
   
   These endpoints are used for monitoring and debugging the adapter.

3. **Proxy Route**:
   ```python
   @app.api_route("/{path:path}", methods=["GET", "POST", "PUT", "DELETE", "OPTIONS", "HEAD", "PATCH"])
   async def proxy(request: Request, path: str):
       """Proxy all other requests to the actual API unchanged."""
       return await handle_proxy(request, path)
   ```
   
   This catch-all route proxies all other API requests to the backend LLM API unchanged, allowing passthrough of requests that don't need format conversion.

### Server Startup

```python
if __name__ == "__main__":
    logger.info(f"Starting API adapter server on {API_ADAPTER_HOST}:{API_ADAPTER_PORT}")
    uvicorn.run(app, host=API_ADAPTER_HOST, port=API_ADAPTER_PORT)
```

This code starts the FastAPI application using Uvicorn when the file is executed directly.

## Integration Points

- **Handlers**: The server delegates request processing to specialized handler functions from the `handlers` module.
- **Configuration**: Server configuration comes from the `config.py` file, which pulls values from environment variables.
- **Models**: Request data is parsed using Pydantic models defined in the `models` directory.

## Request Flow

1. Client sends a request to the adapter
2. The appropriate route handler is invoked
3. For Responses API requests:
   - The request is processed by `handle_responses`
   - Request format is converted if needed
   - Request is forwarded to the LLM API
   - Response is converted back if needed
4. For other requests:
   - The request is proxied directly to the backend LLM API
   - Response is returned to the client

## Dependencies

- FastAPI: Web framework for API development
- Uvicorn: ASGI server for running the FastAPI application
- Pydantic: Data validation and settings management