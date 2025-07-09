# Gemma3n Transformers API Server

OpenAI-compatible API server for the Gemma3n model, optimized for NVIDIA Jetson devices.

## Features

- OpenAI-compatible chat completions API
- Support for text and multimodal (text + image) inputs
- Streaming and non-streaming responses
- Optimized for Jetson GPU inference
- Docker containerization with NVIDIA runtime support
- Automatic model download and caching

## Model Setup

The default model is `google/gemma-3n-e4b`. The model will be automatically downloaded on first run.

### If the model is gated (requires authentication):
1. Get a Hugging Face token from https://huggingface.co/settings/tokens
2. Add it to your `.env` file:
   ```bash
   HF_TOKEN=your_huggingface_token_here
   ```

### Pre-download the model (optional):
To download the model before running the server:
```bash
# Set environment variables
export MODEL_NAME=google/gemma-3n-e4b
export HF_TOKEN=your_token_here  # if needed

# Run the download script
python3 download_model.py
```

## Quick Start

1. Copy the environment file and configure:
```bash
cp .env.example .env
# Edit .env with your settings, especially HF_TOKEN if needed
```

2. Build and run with Docker Compose:
```bash
docker-compose up --build
```

The first run will download the model (several GB), which may take 10-30 minutes depending on your connection.

3. Test the API:
```bash
# Text-only request
curl -X POST http://localhost:8000/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{
    "model": "gemma3n",
    "messages": [{"role": "user", "content": "Hello, how are you?"}]
  }'

# With streaming
curl -X POST http://localhost:8000/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{
    "model": "gemma3n",
    "messages": [{"role": "user", "content": "Tell me a story"}],
    "stream": true
  }'
```

## API Endpoints

- `POST /v1/chat/completions` - Chat completions (OpenAI-compatible)
- `GET /v1/models` - List available models
- `GET /health` - Health check

## Multimodal Support

To send images with your prompts, use the OpenAI format:

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

## Environment Variables

See `.env.example` for all available configuration options.