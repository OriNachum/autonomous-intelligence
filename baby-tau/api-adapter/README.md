# API Adapter

This adapter provides compatibility between OpenAI's Responses API and Chat Completions API formats.

## Overview

Applications can connect to the adapter using either API format:

- **Responses API** → `/v1/responses`
- **Chat Completions API** → `/v1/chat/completions`

The adapter will convert between formats as needed and forward requests to the actual LLM API (Ollama).

## Usage

### Using with Codex

When the adapter is running, you can configure Codex to use it:

```bash
export OPENAI_BASE_URL=http://localhost:8080/v1
export OPENAI_API_KEY=dummy-key
```

### Using directly

You can also make direct API calls to the adapter:

```bash
# Chat Completions API
curl http://localhost:8080/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{
    "model": "mistral",
    "messages": [{"role": "user", "content": "Hello!"}]
  }'

# Responses API
curl http://localhost:8080/v1/responses \
  -H "Content-Type: application/json" \
  -d '{
    "model": "mistral",
    "input": [{"role": "user", "content": "Hello!"}]
  }'
```

### Using from another container

If you have another container that needs to access this API adapter:

```bash
# Set environment variables to point to the adapter
export OPENAI_BASE_URL=http://<host-ip>:8080/v1
export OPENAI_API_KEY=dummy-key
```

## Running with Docker Compose

You can run the adapter using a specific `docker-compose` file, such as `docker-compose-codex.yaml`:

```bash
docker compose -f docker-compose-codex.yaml up
```

```powershell
docker-compose -f docker-compose-codex.yaml up
```


This will start the adapter and any required services defined in the `docker-compose-codex.yaml` file.

## Configuration

The adapter can be configured with these environment variables:

- `OPENAI_BASE_URL`: The URL of the underlying LLM API (default: http://localhost:8000/v1)
- `API_ADAPTER_PORT`: The port to run the adapter on (default: 8080)
- `API_ADAPTER_HOST`: The host interface to bind to (default: 0.0.0.0)

## Testing

To test if the adapter is working correctly:

```bash
# Test Chat Completions endpoint
curl http://localhost:8080/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{
    "model": "mistral",
    "messages": [{"role": "user", "content": "Write a haiku about AI"}]
  }'

# Test Responses endpoint
curl http://localhost:8080/v1/responses \
  -H "Content-Type: application/json" \
  -d '{
    "model": "mistral",
    "input": "Write a haiku about AI"
  }'
```

## Limitations

Current limitations of the adapter:

1. Streaming responses may not be fully compatible between formats
2. Function calling has different formats between the APIs and may require additional handling
3. Complex structured outputs might not be perfectly converted between formats

## Architecture

The adapter runs as a FastAPI server that:

1. Receives API requests in either format
2. Converts the format as needed
3. Forwards to the actual LLM API
4. Receives the response
5. Converts the response back to the original format
6. Returns to the client

This allows applications designed for either API to work with any compatible LLM provider.
