# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

This is an early-stage autonomous intelligence project called "Gemma" that aims to build a multimodal AI assistant with:

- Event-driven architecture using Unix domain sockets
- Real-time camera feed processing with object detection
- Audio processing with VAD (Voice Activity Detection) and wake word detection
- Text-to-speech queue management
- Advanced memory management system with immediate and long-term memory
- Integration with RAG (Retrieval-Augmented Generation) using Milvus and Neo4j

## Architecture Components

The system is designed around several key processing loops:

1. **Event Management**: Central event system for coordinating between modules
2. **Queue Script**: Manages text-to-speech sentence queue with reset capabilities
3. **Camera Feed Loop**: GStreamer-based camera processing with object detection
4. **Sound Feed Loop**: Microphone processing with speech detection and wake word recognition
5. **Text Loop**: Terminal-based text input processing
6. **Main Loop**: Central coordinator that handles model inference and memory management

## Memory Architecture

The system implements a two-tier memory system:

- **Immediate Memory**: Short-term fact distillation and injection for current context
- **Long-term Memory**: Persistent storage using Milvus (vector database) and Neo4j (graph database) for semantic search and retrieval

## Development Status

This repository currently contains only planning documentation. The actual implementation has not yet begun, so there are no build commands, dependencies, or code structure to document at this time.

## Planning Documents

- `docs/plans/initial.md`: Complete system architecture and component specifications