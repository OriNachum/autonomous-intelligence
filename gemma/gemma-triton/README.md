# Gemma-Triton

High-performance inference server for Google's Gemma 3n E4B model using NVIDIA Triton Inference Server with OpenAI-compatible API.

## Features

- **NVIDIA Triton Inference Server**: Optimized for GPU acceleration and high throughput
- **OpenAI-Compatible API**: Drop-in replacement for OpenAI's chat completion endpoints
- **Multimodal Support**: Text and image inputs with base64 encoding
- **Streaming Support**: Real-time token streaming using Triton's decoupled mode
- **Docker Deployment**: Containerized setup for easy deployment
- **Jetson Optimized**: Configured for NVIDIA Jetson devices

## Architecture

The system consists of two main components:

1. **Triton Inference Server**: Hosts the Gemma 3n model with Python backend
2. **FastAPI Gateway**: Provides OpenAI-compatible REST API endpoints

```
Client → FastAPI Gateway → Triton Server → Gemma 3n Model
```

## Quick Start

### Prerequisites

- NVIDIA GPU with CUDA support
- Docker with NVIDIA Container Runtime
- HuggingFace account (for model access)

### Setup

1. Clone the repository:
```bash
git clone <repository>
cd gemma-triton
```

2. Set your HuggingFace token (optional, for gated models):
```bash
export HF_TOKEN=your_huggingface_token
```

3. Build and start the services:
```bash
docker-compose up --build
```

### Usage

The API will be available at `http://localhost:8080` with OpenAI-compatible endpoints.

#### Text Generation

```bash
curl -X POST "http://localhost:8080/v1/chat/completions" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "gemma3n",
    "messages": [
      {"role": "user", "content": "Hello, how are you?"}
    ],
    "max_tokens": 100,
    "temperature": 0.7
  }'
```

#### Multimodal (Text + Image)

```bash
curl -X POST "http://localhost:8080/v1/chat/completions" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "gemma3n",
    "messages": [
      {
        "role": "user",
        "content": [
          {"type": "text", "text": "What do you see in this image?"},
          {"type": "image_url", "image_url": {"url": "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNkYPhfDwAChwGA60e6kgAAAABJRU5ErkJggg=="}}
        ]
      }
    ],
    "max_tokens": 100
  }'
```

#### Streaming

```bash
curl -X POST "http://localhost:8080/v1/chat/completions" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "gemma3n",
    "messages": [
      {"role": "user", "content": "Tell me a story"}
    ],
    "stream": true,
    "max_tokens": 200
  }'
```

## API Endpoints

### Chat Completions

`POST /v1/chat/completions`

OpenAI-compatible chat completion endpoint.

**Parameters:**
- `model` (string): Model name (use "gemma3n")
- `messages` (array): Array of message objects
- `temperature` (float, optional): Sampling temperature (0.0-2.0)
- `max_tokens` (int, optional): Maximum tokens to generate
- `top_p` (float, optional): Top-p sampling parameter
- `stream` (bool, optional): Enable streaming response
- `frequency_penalty` (float, optional): Frequency penalty (accepted but not used)
- `presence_penalty` (float, optional): Presence penalty (accepted but not used)

### Models

`GET /v1/models`

List available models.

### Health Check

`GET /health`

Check server health and model status.

## Configuration

### Environment Variables

#### Triton Server
- `MODEL_NAME`: HuggingFace model name (default: "google/gemma-3n-e4b")
- `HF_TOKEN`: HuggingFace access token
- `NVIDIA_VISIBLE_DEVICES`: GPU devices to use

#### API Server
- `TRITON_HTTP_URL`: Triton HTTP endpoint (default: "triton:8000")
- `TRITON_GRPC_URL`: Triton gRPC endpoint (default: "triton:8001")
- `API_PORT`: API server port (default: "8080")

### Model Configuration

The Triton model configuration is in `model_repository/gemma3n/config.pbtxt`:

- **Backend**: Python backend with decoupled transaction policy
- **Inputs**: prompt, images, max_tokens, temperature, top_p, stream
- **Outputs**: text
- **Instance**: Single GPU instance with dynamic batching

## Deployment

### Docker Compose (Recommended)

```yaml
version: '3.8'
services:
  triton:
    build:
      context: .
      dockerfile: Dockerfile.triton
    runtime: nvidia
    environment:
      - MODEL_NAME=google/gemma-3n-e4b
      - HF_TOKEN=${HF_TOKEN}
    ports:
      - "8000:8000"
      - "8001:8001"
      - "8002:8002"
    
  api:
    build:
      context: .
      dockerfile: Dockerfile.api
    depends_on:
      - triton
    ports:
      - "8080:8080"
```

### Manual Deployment

1. Build Triton container:
```bash
docker build -f Dockerfile.triton -t gemma-triton .
```

2. Run Triton server:
```bash
docker run --gpus all -p 8000:8000 -p 8001:8001 -p 8002:8002 gemma-triton
```

3. Build API container:
```bash
docker build -f Dockerfile.api -t gemma-triton-api .
```

4. Run API server:
```bash
docker run -p 8080:8080 --network host gemma-triton-api
```

## Performance Optimization

### GPU Memory Management

The model uses `torch.bfloat16` on CUDA for memory efficiency. For larger models, consider:

- Adjusting `max_batch_size` in config.pbtxt
- Using model parallelism for multi-GPU setups
- Implementing model quantization

### Batching

Dynamic batching is enabled by default. Configure in `config.pbtxt`:

```protobuf
dynamic_batching {
  max_queue_delay_microseconds: 100
  preferred_batch_size: [1, 2, 4]
}
```

## Troubleshooting

### Common Issues

1. **CUDA Out of Memory**: Reduce batch size or use smaller model variant
2. **Model Download Timeout**: Increase timeout or pre-download model
3. **Permission Errors**: Ensure Docker has GPU access and proper permissions

### Debugging

Enable debug logging:
```bash
export TRITON_LOG_LEVEL=2
```

Check Triton server status:
```bash
curl http://localhost:8000/v2/health/ready
```

Check model status:
```bash
curl http://localhost:8000/v2/models/gemma3n/ready
```

## Development

### Adding New Models

1. Create new model directory in `model_repository/`
2. Add `config.pbtxt` with model configuration
3. Implement `model.py` with model loading and inference logic
4. Update API server to handle new model name

### Custom Preprocessing

Modify the `format_messages_to_prompt` function in `src/server.py` to customize how messages are formatted for the model.

## License

This project is licensed under the MIT License. See LICENSE file for details.

## Contributing

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Add tests if applicable
5. Submit a pull request

## Support

For issues and questions:
- Check the troubleshooting section
- Review Triton Inference Server documentation
- Open an issue on GitHub