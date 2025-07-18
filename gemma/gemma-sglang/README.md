# Gemma 3n SGLang API

OpenAI-compatible API server for Gemma 3n multimodal model using SGLang backend.

## Features

- OpenAI API v1 compatible endpoints
- Multimodal support (text, images, audio)
- Streaming and non-streaming responses
- Docker containerized deployment
- NVIDIA Jetson optimization

## Quick Start

### Prerequisites

- Docker and Docker Compose
- NVIDIA GPU with Docker runtime
- SGLang compatible container environment

### Download Model

```bash
# Set your Hugging Face token
export HF_TOKEN="your_hf_token_here"

# Download Gemma 3n model
python download_model.py
```

### Start Services

For standard GPU systems:
```bash
docker-compose up --build
```

For NVIDIA Jetson:
```bash
docker-compose -f docker-compose.jetson.yml up --build
```

### Test API

```bash
# Test health endpoint
curl http://localhost:8080/health

# Test chat completion
curl -X POST http://localhost:8080/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{
    "model": "gemma3n",
    "messages": [
      {"role": "user", "content": "Hello! How are you?"}
    ]
  }'
```

### Multimodal Examples

Text + Image:
```bash
curl -X POST http://localhost:8080/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{
    "model": "gemma3n",
    "messages": [
      {
        "role": "user",
        "content": [
          {"type": "text", "text": "What do you see in this image?"},
          {"type": "image_url", "image_url": {"url": "data:image/jpeg;base64,..."}}
        ]
      }
    ]
  }'
```

## Configuration

Environment variables:

- `SGLANG_URL`: SGLang server URL (default: http://localhost:30000)
- `MODEL_NAME`: Model identifier (default: gemma3n)
- `HOST`: Server host (default: 0.0.0.0)
- `PORT`: Server port (default: 8080)
- `ENABLE_AUDIO`: Enable audio processing (default: true)
- `HF_TOKEN`: Hugging Face token for model download

## API Endpoints

- `POST /v1/chat/completions` - Chat completions
- `GET /v1/models` - List available models
- `GET /health` - Health check

## Development

Install dependencies:
```bash
pip install -r requirements.txt
```

Run locally:
```bash
python app.py
```

## Architecture

The system consists of two main components:

1. **SGLang Backend**: Handles actual model inference
2. **FastAPI Gateway**: Provides OpenAI-compatible API interface

The FastAPI server processes incoming requests, handles multimodal content, and forwards to the SGLang backend for inference.