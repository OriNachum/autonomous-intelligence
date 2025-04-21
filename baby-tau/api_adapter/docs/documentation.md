# API Adapter Documentation

## Overview

The API Adapter is a service that provides a compatibility layer between requests from a client that uses Responses api to AI Providers that only support chat.completions endpoints.

Any tooling must be handled by the client that configures them. The adapter's responsibility is to relay the correct events in responses api format and as expected (see events-conversion-guidance.md file)

## Flow Diagram

```
Client Request → API Adapter (FastAPI) → Format Conversion → LLM API → Response → Format Conversion → Client
```

## Environment Configuration

The adapter uses the following environment variables:

- `OPENAI_BASE_URL_INTERNAL`: URL of the LLM API (default: http://localhost:8000)
- `OPENAI_BASE_URL`: URL where this adapter is accessible (default: http://localhost:8080)





