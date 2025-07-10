# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project: Gemma3n Transformers API Server

This project implements an OpenAI-compatible API server for the Gemma3n model (`google/gemma-3n-e4b`), optimized for NVIDIA Jetson devices with support for text and multimodal (text + image) inputs.

## Commands

### Development
```bash
# Run linting
ruff check .

# Format code
ruff format .

# Run tests (when available)
pytest tests/
```

### Docker Operations
```bash
# Build and run the server
docker compose up --build

# Stop and remove volumes (clears model cache)
docker compose down -v

# View logs
docker compose logs -f gemma3n-api
```

### Testing API
```bash
# Test text-only request
curl -X POST http://localhost:8000/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{"model": "gemma3n", "messages": [{"role": "user", "content": "Hello"}]}'

# Test streaming
curl -X POST http://localhost:8000/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{"model": "gemma3n", "messages": [{"role": "user", "content": "Tell me a story"}], "stream": true}'

# Test model download script
python test_download.py
```

## Architecture

### Core Components
1. **app.py** - FastAPI server exposing OpenAI-compatible endpoints
   - `/v1/chat/completions` - Main chat endpoint (streaming/non-streaming)
   - `/v1/models` - List available models
   - `/health` - Health check

2. **model_handler.py** - Model management and inference
   - Loads Gemma3n using Hugging Face Transformers
   - Handles multimodal inputs (text + images)
   - Optimized for GPU inference on Jetson devices

3. **download_model.py** - Pre-download script
   - Downloads models to cache before server startup
   - Prevents timeout issues during first API calls

4. **entrypoint.sh** - Docker entrypoint
   - Manages model caching and server startup
   - Ensures models are available before API starts

### Docker Architecture
- Based on Jetson-optimized PyTorch image (`dustynv/pytorch:2.1-r36.2.0`)
- Named volumes for persistent model storage (`gemma3n-hf-cache`)
- NVIDIA runtime for GPU access
- Host network mode for performance

### Model Storage
- Models are automatically downloaded on first run
- Stored in Docker volumes that persist across container restarts
- Volume location: `/models` inside container
- No re-download needed unless volumes are explicitly removed

## Environment Variables

Key variables (see `.env.example` for full list):
- `MODEL_NAME` - Model identifier (default: `google/gemma-3n-e4b`)
- `GEMMA3N_PORT` - API server port (default: 8000)
- `HF_TOKEN` - Hugging Face token for gated models
- `MAX_LENGTH` - Maximum generation length (default: 2048)
- `TEMPERATURE` - Default temperature (default: 0.7)

## Multimodal Support

Images can be sent using OpenAI format:
```json
{
  "model": "gemma3n",
  "messages": [{
    "role": "user",
    "content": [
      {"type": "text", "text": "What's in this image?"},
      {"type": "image_url", "image_url": {"url": "data:image/jpeg;base64,..."}}
    ]
  }]
}
```

## Key Implementation Details

- Streaming responses use Server-Sent Events (SSE)
- Model loading is lazy (on first request) unless pre-downloaded
- GPU memory is managed automatically by PyTorch
- API is fully compatible with OpenAI client libraries