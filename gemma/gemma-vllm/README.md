# Gemma 3n vLLM Demo CLI

Simple command-line demo for testing Gemma 3n multimodal model capabilities using vLLM on NVIDIA Jetson devices.

## Features

- **Multimodal Support**: Text, image, and audio input processing
- **Simple CLI**: Single command execution with file inputs
- **Docker Integration**: Complete containerized setup with vLLM backend
- **Jetson Optimized**: Configured for NVIDIA Jetson devices

## Quick Start

### Prerequisites

- NVIDIA Jetson device with Docker support
- Docker and Docker Compose installed
- HuggingFace account and token

### Setup

1. **Clone and Setup Environment**:
```bash
cd gemma-vllm
cp .env.sample .env
# Edit .env and add your HF_TOKEN=your_token_here
```

2. **Download Model** (Optional - will auto-download if not present):
```bash
python download_model.py --model fp16
```

3. **Start Services**:
```bash
docker compose up -d vllm
```

### Usage

The simplest way to run demos is using the provided wrapper script:

```bash
# Text only
./run_demo.sh --text "Hello, how are you?"

# Text + Image
./run_demo.sh --text "What do you see in this image?" --image photo.jpg

# Text + Multiple Images  
./run_demo.sh --text "Compare these images" --image img1.jpg --image img2.jpg

# Text + Audio (if supported)
./run_demo.sh --text "Transcribe this audio" --audio recording.wav

# All modalities
./run_demo.sh --text "Analyze this content" --image photo.jpg --audio audio.wav
```

### Direct Python Usage

You can also run the CLI directly:

```bash
# Start vLLM service first
docker compose up -d vllm

# Run CLI in container
docker compose run --rm demo-cli python demo_cli.py --text "Hello world"
```

## API Endpoints

When vLLM service is running, it provides OpenAI-compatible endpoints:

- **Chat Completions**: `POST http://localhost:8000/v1/chat/completions`
- **Health Check**: `GET http://localhost:8000/health`
- **Models**: `GET http://localhost:8000/v1/models`

## Configuration

### Environment Variables

- `HF_TOKEN`: HuggingFace token (required)
- `MODEL_PATH`: Model directory path (default: `/models/gemma3n`)
- `VLLM_URL`: vLLM server URL (default: `http://localhost:8000`)
- `MODEL_NAME`: Model identifier (default: `gemma3n`)

### Model Options

- **fp16** (default): `muranAI/gemma-3n-e4b-it-fp16` - Recommended for Jetson
- **full**: `google/gemma-3n-E4B` - Full precision model

## File Structure

```
gemma-vllm/
├── demo_cli.py           # Main CLI script
├── run_demo.sh          # Convenience wrapper script  
├── download_model.py    # Model download utility
├── docker compose.yml   # Docker services configuration
├── Dockerfile           # CLI container definition
├── requirements.txt     # Python dependencies
├── .env.sample         # Environment template
└── examples/           # Example input files
```

## Troubleshooting

### vLLM Service Issues

```bash
# Check service status
docker compose ps

# View vLLM logs
docker compose logs vllm

# Restart services
docker compose restart vllm
```

### Model Download Issues

```bash
# Check available models
python download_model.py --list

# Re-download model
python download_model.py --model fp16
```

### Memory Issues

For Jetson devices with limited memory:
- Use the fp16 model variant
- Reduce `--max-model-len` in docker compose.yml
- Monitor GPU memory with `nvidia-smi`

## Examples Directory

Create an `examples/` directory with sample files:

```bash
mkdir -p examples inputs
# Add sample images, audio files for testing
```

## Model Information

- **Base Model**: Gemma 3n-E4B (Google)
- **Capabilities**: Text, Image, Audio → Text
- **Recommended Variant**: muranAI/gemma-3n-e4b-it-fp16
- **Backend**: vLLM with OpenAI-compatible API

## Development

To extend or modify the CLI:

1. Edit `demo_cli.py` for CLI functionality
2. Modify `docker compose.yml` for service configuration  
3. Update `requirements.txt` for new dependencies
4. Test with `./run_demo.sh`