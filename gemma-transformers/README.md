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

The default model is `google/gemma-3n-e4b`. Everything is containerized - the model will be automatically downloaded on first run and stored in Docker volumes.

### Persistent Model Storage
- Models are stored in named Docker volumes (`gemma3n-hf-cache`)
- Once downloaded, models persist across container restarts
- No need to re-download unless you explicitly remove the volumes

### If the model is gated (requires authentication):
1. Get a Hugging Face token from https://huggingface.co/settings/tokens
2. Add it to your `.env` file:
   ```bash
   HF_TOKEN=your_huggingface_token_here
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

The first run will download the model (several GB), which may take 10-30 minutes. Subsequent runs will use the cached model and start in seconds.

### Managing Model Storage

View volume information:
```bash
docker volume ls | grep gemma3n
docker volume inspect gemma3n-hf-cache
```

Remove cached models (to re-download):
```bash
docker-compose down -v  # Removes all volumes
# OR
docker volume rm gemma3n-hf-cache  # Remove only model cache
```

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