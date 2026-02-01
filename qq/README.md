# qq - Quick Question CLI

*Quick Question* is there to reside on your device and assist however it can.
It remembers, it can read files, MCPs and Skills.

## Quick Start

```bash
# Install dependencies
uv sync

# Run in console mode
./qq

# Run with a specific agent
./qq --agent coder

# One-shot CLI mode
./qq -m "Explain Python GIL"

# Global installation
sudo ln -sf $(pwd)/qq /usr/local/bin/qq
```

## Features

- **Colored Console UI** - Rich terminal interface with markdown rendering
- **Conversation History** - 20-message sliding window with persistence
- **Agent System** - Load agents from `agents/<name>/<name>.system.md`
- **Skills** - Auto-inject relevant skills based on message keywords
- **MCP Tools** - Load external tools from `mcp.json`
- **Memory** - Notes storage (MongoDB) and knowledge graph (Neo4j)
- **Prefix Caching** - Optimized for vLLM's prefix caching

## Memory Services

For persistent memory (notes and knowledge graph), start the services:

```bash
docker compose up -d
```

This starts:
- **MongoDB** (port 27017) - Notes storage with vector embeddings
- **Neo4j** (port 7474/7687) - Knowledge graph

Check status with `qq-memory` or `qq-test`.

<img width="1109" height="1065" alt="image" src="https://github.com/user-attachments/assets/4a5211d1-e832-421c-9398-45477d0eba1c" />


## Configuration

Copy `.env` and configure:
- `VLLM_URL` - vLLM endpoint (default: `http://localhost:8100/v1`)
- `MODEL_ID` - Model name
- `HISTORY_DIR` - History storage location
- `MONGODB_URI` - MongoDB connection (default: `mongodb://localhost:27017`)
- `NEO4J_URI` - Neo4j connection (default: `bolt://localhost:7687`)

## Structure

```
qq/
├── agents/          # Agent definitions
│   └── default/
├── skills/          # Skill files
│   └── coding/
├── src/qq/          # Source code
├── data/            # Docker volumes (gitignored)
└── mcp.json         # MCP tool configuration
```

