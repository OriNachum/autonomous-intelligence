# Gemma - Multimodal AI Assistant

## Overview

Gemma is a real-time multimodal AI assistant designed to process camera, audio, and text inputs simultaneously. The system uses event-driven architecture with Unix domain sockets and targets 400ms response time for natural interaction.

## Core Architecture

### Event System
- **Implementation**: Unix domain sockets (custom implementation, see ../TauLegacy/)
- **Priority**: Latest events take precedence
- **Throughput**: TBD

### Processing Loops
The system consists of 6 concurrent processing loops:

1. **Event Management Module**: Raise/consume Unix domain events
2. **Queue Script**: Manages TTS sentence queue with `queue sentences` and `reset queue` events
3. **Camera Feed Loop**: GStreamer camera processing with object detection
4. **Sound Feed Loop**: Microphone processing with VAD and wake word detection
5. **Text Loop**: Terminal text input processing
6. **Main Loop**: Event coordination and model inference

## Input Processing

### Camera Processing
- **Model**: Yolov6 object detection
- **Focus**: Humans and animals detection
- **Frame Rate**: TBD
- **Behavior**: Send current frame + object change events (appear/disappear)

### Audio Processing
- **VAD Model**: SileroVAD (Jetson-containers supported)
- **Wake Words**: "Gemma" or "Hey Gemma"
- **Noise Filtering**: TBD (possibly headset-native)
- **Quality**: TBD sampling rate
- **Behavior**: Emit events only on speech detection or wake word

### Text Processing
- **Input**: Terminal text entry (press enter to send)
- **Integration**: Feeds into main event loop

## AI Model & Inference

### Primary Model
- **Model**: Gemma 3n (multimodal: image + audio + text → text)
- **Input**: Always sends all 3 modalities simultaneously
- **History**: 20 messages
- **Response Target**: 400ms to first spoken word

### Response Format
- **Speech Output**: Only content in quotations is spoken to user
- **Actions**: Asterisk-marked actions (*Looking at the user*)
- **Future Extension**: Action execution system for robotic control

### Real-time Implementation
Streaming approach for 400ms target:
1. Model outputs sentences in quotations
2. TTS processes quoted content immediately
3. Speech generation and playback run in parallel
4. Next sentence ready before current finishes

## Memory System

### Immediate Memory (50-100 facts)
- **Archival Decision**: Gemma 3n with different instructions
- **Lifecycle**: 
  - Distill facts after response generation
  - Archive old facts to long-term storage
  - Inject current facts into next request

### Long-term Memory
- **Vector Storage**: Milvus with sentence embeddings
- **Graph Storage**: Neo4j (structure TBD, possibly model-managed)
- **Embedding Model**: TBD (Vllm or Ollama compatible)
- **Retrieval**: Semantic search on new prompts
- **Interruption**: Small decision model can stop current speech to inject relevant memories

## Output & Speech

### Text-to-Speech
- **Engine**: KokoroTTS (Jetson-containers supported)
- **Queue Management**: 
  - Sentences queued and processed in parallel
  - Max tokens cap prevents overflow
  - `reset queue` stops current speech

### Speech Queue Behavior
- While queue has content: read then dequeue
- If `reset queue` event: stop current read immediately

## Deployment

### Hardware Requirements
- AGX 64GB Jetson
- Microphone
- Speakers  
- Camera

### Architecture
- **Orchestration**: Different applications, possibly separate Docker containers
- **Data Sharing**: Shared volumes between containers
- **Monitoring**: Python logger
- **Failure Handling**: TBD

## Implementation Notes

### Performance Targets
- **Response Time**: 400ms to first spoken word
- **Memory Size**: 50-100 immediate facts
- **Message History**: 20 messages

### Undecided Items
- Event throughput/latency requirements
- Camera frame rates and audio quality specs
- Memory relevance scoring algorithms
- Embedding model selection
- Component failure handling strategies


