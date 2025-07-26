# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

This is a vLLM-based implementation for running Gemma 3n-E4B multimodal model demos on NVIDIA Jetson devices. The project aims to create a simple CLI tool that accepts text, audio, and image inputs and returns text responses using the Gemma 3n model through vLLM.

## Architecture

- **Target Model**: Gemma 3n-E4B multimodal model (text, audio, image → text)
- **Backend**: vLLM for model serving
- **Container Runtime**: jetson-containers Docker environment
- **Platform**: NVIDIA Jetson devices
- **Interface**: Simple CLI (not chat-based)

## Key Components

- **Model Sources**:
  - Primary: `google/gemma-3n-E4B` (https://huggingface.co/google/gemma-3n-E4B)
  - Quantized: `muranAI/gemma-3n-e4b-it-fp16` (supports all modalities)
- **Infrastructure**: Docker Compose + vLLM server
- **CLI Interface**: Single script accepting multiple modality inputs

## Environment Setup

- **Required Environment Variables**:
  - `HF_TOKEN`: Hugging Face token (configured in `.env`)
- **Docker**: Uses jetson-containers base images with vLLM package
- **vLLM Definition**: Located at `/home/orin/git/jetson-containers/packages/llm/vllm`

## Development Context

This project is part of a larger Gemma implementation suite including:
- gemma-transformers (✅ complete)
- gemma-sglang (✅ complete) 
- gemma-triton (in progress)
- gemma-vllm (⏳ this project)
- gemma-ollama (⏳ planned)

The gemma-sglang implementation provides a reference for multimodal API structure and Docker configuration patterns.

## Implementation Goals

Create a demonstration CLI that:
1. Accepts command-line arguments for text, audio files, and image files
2. Processes inputs through vLLM-served Gemma 3n model
3. Returns text responses
4. Runs via single script + docker-compose execution
5. Supports all three modalities (text, audio, image)