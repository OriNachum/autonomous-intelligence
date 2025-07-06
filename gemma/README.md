# Gemma - Multimodal AI Assistant

A real-time multimodal AI assistant designed to process camera, audio, and text inputs simultaneously using an event-driven architecture.

## Features

- **Event-driven Architecture**: Unix domain sockets for high-performance component communication
- **Real-time Camera Processing**: GStreamer-based camera feed with YOLOv6 object detection
- **Advanced Audio Processing**: Voice Activity Detection (VAD) and wake word recognition
- **Text-to-Speech Queue**: Sentence-level TTS processing with reset capabilities
- **Multimodal AI Model**: Gemma 3n integration for simultaneous image, audio, and text processing
- **Memory System**: Immediate fact distillation and long-term storage (planned)

## Architecture

The system consists of 6 concurrent processing loops:

1. **Event Management**: Central Unix domain socket event system
2. **Queue Manager**: TTS sentence queue with priority handling
3. **Camera Processor**: GStreamer camera processing with object detection
4. **Sound Processor**: Microphone processing with VAD and wake word detection
5. **Text Processor**: Terminal text input processing
6. **Main Loop**: Event coordination and model inference

## Installation

### Prerequisites

- Python 3.8+
- AGX 64GB Jetson (recommended) or compatible hardware
- Camera, microphone, speakers
- CUDA-capable GPU (optional but recommended)

### Dependencies

```bash
pip install -r requirements.txt
```

### Hardware Setup

Ensure your hardware is connected:
- Camera (USB or CSI)
- Microphone
- Speakers or headphones

## Configuration

Configuration can be set via environment variables or the `Config` class:

```bash
export GEMMA_CAMERA_DEVICE=0
export GEMMA_AUDIO_SAMPLE_RATE=16000
export GEMMA_WAKE_WORDS="Gemma,Hey Gemma"
export GEMMA_TTS_ENGINE="kokoro"
```

## Usage

### Quick Start

```bash
./run_gemma.py
```

### Manual Start

```bash
python -m src.gemma
```

### Text Commands

While running, you can use these text commands:

- `/help` - Show help
- `/status` - Show system status
- `/clear` - Clear screen
- `/history` - Show input history
- `/reset` - Reset conversation
- `/quit` - Exit application

## Component Status

### ✅ Implemented
- [x] Project structure and configuration
- [x] Event management system with Unix domain sockets
- [x] TTS queue management with sentence processing
- [x] Camera processing with GStreamer and YOLOv6
- [x] Sound processing with VAD and wake word detection
- [x] Text input processing with terminal interface
- [x] Main coordination loop with model interface
- [x] Response processing and TTS integration

### 🚧 In Progress
- [ ] Immediate memory system with fact distillation
- [ ] Long-term memory with Milvus and Neo4j
- [ ] Docker containerization

### 📋 Planned
- [ ] Advanced memory retrieval and injection
- [ ] Robotic action execution system
- [ ] Performance optimization for 400ms response target
- [ ] Web interface for monitoring
- [ ] Advanced model fine-tuning

## Performance Targets

- **Response Time**: 400ms to first spoken word
- **Memory Size**: 50-100 immediate facts
- **Message History**: 20 messages
- **Frame Rate**: 30fps camera processing
- **Audio**: 16kHz sample rate

## Development

### Project Structure

```
gemma/
├── src/
│   ├── event_system/       # Unix domain socket event management
│   ├── queue_manager/      # TTS queue processing
│   ├── camera_processor/   # Camera and object detection
│   ├── sound_processor/    # Audio processing and VAD
│   ├── text_processor/     # Terminal text input
│   ├── main_loop/          # Coordination and model inference
│   ├── memory_system/      # Memory management (planned)
│   ├── models/             # Model interfaces
│   ├── config.py           # Configuration management
│   └── gemma.py            # Main application
├── docs/
│   └── plans/              # Architecture and planning docs
├── requirements.txt
└── run_gemma.py           # Startup script
```

### Adding New Components

1. Create component directory under `src/`
2. Implement event producer/consumer interfaces
3. Register with main application
4. Update configuration as needed

## Troubleshooting

### Common Issues

1. **Camera not found**: Check device permissions and driver installation
2. **Audio device error**: Verify microphone permissions and ALSA configuration
3. **Model loading fails**: Ensure sufficient GPU memory and model files
4. **Socket permission denied**: Check `/tmp` directory permissions

### Debugging

Enable debug logging:
```bash
export GEMMA_LOG_LEVEL=DEBUG
```

## Contributing

1. Fork the repository
2. Create a feature branch
3. Implement changes with tests
4. Submit a pull request

## License

[License information to be added]

## Acknowledgments

- SileroVAD for voice activity detection
- YOLOv6 for object detection
- GStreamer for camera processing
- Jetson containers for deployment support