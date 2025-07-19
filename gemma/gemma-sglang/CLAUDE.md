# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Context

This is the **gemma-sglang** subproject, part of a larger autonomous intelligence ecosystem. It's currently a placeholder/planned implementation for SGLang-based Gemma 3n inference. The parent `gemma/` directory contains three other fully-implemented subprojects:

- **gemma-chat**: Complex multimodal AI assistant with event-driven architecture
- **gemma-transformers**: OpenAI-compatible API server using Transformers
- **gemma-triton**: High-performance Triton inference server

## Current Status

The gemma-sglang directory is mostly empty with only basic documentation. The intended implementation would use jetson-containers to build an SGLang-based Gemma inference server.

## Planned Architecture

Based on sibling projects, this should become:
- SGLang-based inference engine for Gemma 3n model
- Multimodal support (text + vision)
- NVIDIA Jetson optimization
- Docker containerized deployment
- Likely FastAPI gateway similar to gemma-triton

## Build Commands

The main build command documented is:
```bash
CUDA_VERSION=12.9 LSB_RELEASE=24.04 jc build --skip-tests all --name gemma-3n-sglang sglang
```

Where `jc` refers to jetson-containers build system.

## Development Environment

This project targets NVIDIA Jetson hardware (especially AGX 64GB) but should work on standard GPU setups. All sibling projects use:
- Docker/Docker Compose for containerization
- Python with asyncio for async operations
- Environment variables for configuration
- Volume mounts for model persistence

## Sister Project Commands (for reference)

If implementing similar patterns to other gemma projects:

**Testing patterns:**
```bash
ruff check .
ruff format .
pytest tests/
```

**Docker patterns:**
```bash
docker-compose up --build
docker-compose -f docker-compose.jetson.yml up
```

**API testing pattern:**
```bash
curl -X POST http://localhost:8080/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{"model": "gemma3n", "messages": [{"role": "user", "content": "Hello"}]}'
```

## Implementation Notes

When developing this project:
- Follow the multimodal patterns established in gemma-transformers
- Use similar Docker containerization strategy as gemma-triton
- Implement OpenAI-compatible API endpoints for consistency
- Optimize for Jetson hardware constraints
- Support both text and vision inputs for Gemma 3n multimodal capabilities

## Documentation Instructions

When working on user requests:
- Save any request plans under `/docs/plans/*.md`
- When finishing a request, document the implementation in `/docs/summary/*.md`