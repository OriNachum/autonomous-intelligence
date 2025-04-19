# API Adapter Documentation

## Overview

The API Adapter is a service that provides a compatibility layer between different API formats, specifically focusing on translating between the OpenAI Responses API and Chat Completions API. This allows applications designed for either API format to work with any compatible LLM provider.

## Directory Structure

```
api-adapter/
├── __init__.py               # Package initialization
├── adapter-readme.md         # Additional adapter documentation
├── codex-readme.md           # Codex-specific documentation
├── config.py                 # Configuration settings and environment variables
├── converter.py              # Format conversion utilities
├── main.py                   # Simplified entry point (partial implementation)
├── message_processor.py      # Processes input messages for conversion
├── models/                   # Data models and schema definitions
│   ├── __init__.py
│   └── requests.py           # Request data models
├── requirements.txt          # Package dependencies
├── response_handler.py       # Handles API response processing
├── run_server.py             # Server entry point script
├── server.py                 # Main FastAPI application and route definitions
├── stream_processor.py       # Handles streaming responses
├── test-adapter.sh           # Script for testing the adapter
├── update-adapter.sh         # Script for updating the adapter
├── utils/                    # Utility functions organized by category
│   ├── __init__.py
│   ├── conversion_utils.py   # Format conversion helpers
│   ├── logging_utils.py      # Logging functionality
│   └── streaming.py          # Streaming utilities
└── handlers/                 # Request handlers organized by endpoint type
    ├── __init__.py
    ├── debug_handler.py      # Debug endpoint handlers
    ├── proxy_handler.py      # API proxy handlers
    └── responses_handler.py  # Responses API handlers
```

## Core Components

### Server (server.py)

The server.py file is the main FastAPI application that defines all API routes and their handlers. It sets up:

1. CORS middleware to handle cross-origin requests
2. Routes for the Responses API endpoints
3. Debug endpoints for monitoring and troubleshooting
4. A catch-all proxy route that forwards requests to the actual LLM API

### Handlers

The handlers are organized by endpoint type:

- **responses_handler.py**: Handles the /v1/responses endpoint
- **proxy_handler.py**: Proxies all other requests to the backend API
- **debug_handler.py**: Provides endpoints for debugging and monitoring

### Models

The models directory contains the Pydantic models that define the structure of requests and responses:

- **requests.py**: Defines the ResponseRequest model and related data structures

### Utils

The utils directory contains utility functions grouped by purpose:

- **conversion_utils.py**: Functions to convert between API formats
- **logging_utils.py**: Functions for request/response logging
- **streaming.py**: Utilities for handling streaming responses

## Flow Diagram

```
Client Request → API Adapter (FastAPI) → Format Conversion → LLM API → Response → Format Conversion → Client
```

## Environment Configuration

The adapter uses the following environment variables:

- `OPENAI_BASE_URL_INTERNAL`: URL of the LLM API (default: http://localhost:8000)
- `OPENAI_BASE_URL`: URL where this adapter is accessible (default: http://localhost:8080)





