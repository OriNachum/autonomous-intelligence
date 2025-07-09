# Claude.md - Project Documentation

## Project: Gemma3n Transformers API Server

This project implements a web server that exposes the Gemma3n model through an OpenAI-compatible API interface, with support for optional image prompts, containerized for NVIDIA Jetson devices.

### Key Components

1. **Python API Server** (`app.py`)
   - FastAPI-based web server
   - OpenAI API-compatible chat completions endpoint
   - Support for text and multimodal (text + image) inputs
   - Streaming and non-streaming responses

2. **Model Handler** (`model_handler.py`)
   - Loads and manages the Gemma3n model using Hugging Face Transformers
   - Handles text generation and image processing
   - Optimized for Jetson GPU inference

3. **Docker Configuration**
   - Dockerfile based on Jetson containers
   - Docker Compose setup for easy deployment
   - GPU support and proper CUDA configuration

### Commands

- **Run tests**: `pytest tests/`
- **Lint code**: `ruff check .`
- **Format code**: `ruff format .`
- **Build Docker image**: `docker build -t gemma3n-api .`
- **Run with Docker Compose**: `docker-compose up`

### Environment Variables

- `MODEL_NAME`: Gemma3n model identifier (default: "google/gemma3n")
- `PORT`: API server port (default: 8000)
- `MAX_LENGTH`: Maximum generation length (default: 2048)
- `TEMPERATURE`: Default temperature for generation (default: 0.7)

### API Endpoints

- `POST /v1/chat/completions`: OpenAI-compatible chat completions
- `GET /health`: Health check endpoint
- `GET /v1/models`: List available models

### Development Notes

- The model supports both text-only and multimodal inputs
- Image inputs should be provided as base64-encoded strings in the OpenAI format
- Streaming responses use Server-Sent Events (SSE)
- The implementation is optimized for Jetson devices with GPU acceleration