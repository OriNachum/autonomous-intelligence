# qq - Quick Question CLI

*Quick Question* is there to reside on your device and assist however it can.
It remembers, it can read files, MCPs and Skills.

## Features

- **Colored Console UI**: Rich terminal interface with markdown rendering.
- **Conversation History**: Persistent context window.
- **Agent System**: Dynamic loading of specialized agents.
- **Skills**: Automatic injection of capability sets ("Skills").
- **MCP Integration**: support for Model Context Protocol tools.
- **Memory**: specialized 3-layer memory with Notes agent, RAG and GraphRAG for long-term retention.


## Setup

### Prerequisites
- **Python**: >= 3.10
- **uv**: Python package and project manager
- **Docker**: For memory services (MongoDB, Neo4j)

### Installation

1.  **Clone the repository**:
    ```bash
    git clone https://github.com/orinachum/autonomous-intelligence.git
    cd autonomous-intelligence/qq
    ```

2.  **Install dependencies**:
    ```bash
    uv sync
    ```

3.  **Configure Environment**:
    Copy the example environment file and edit it:
    ```bash
    cp .env.example .env
    ```
    Key variables:
    - `VLLM_URL`: Your LLM endpoint (e.g., `http://localhost:8100/v1`)
    - `MODEL_ID`: The model name to use.
    - `MONGODB_URI`: `mongodb://localhost:27017`
    - `NEO4J_URI`: `bolt://localhost:7687`

4.  **Start Services**:
    For full functionality (Memory & Knowledge Graph), start the backend services:
    ```bash
    docker compose up -d
    ```

## Getting Started

### Interactive Console
The main way to use QQ is through its rich interactive console:

```bash
./qq
```
This opens a chat interface where you can:
- Chat with the AI.
- Use slash commands (explore with `/`).
- Paste code and files for analysis.

### CLI Mode
For quick, one-off tasks strings without entering the console:

```bash
# Ask a quick question
./qq -m "Explain the relationship between quantum mechanics and general relativity"

# Run with a specific specialized agent
./qq --agent coder -m "Refactor this file..."
```

## Documentation

- [Architecture Overview](docs/architecture.md): High-level system design.
- [Plans](docs/plans/): Active and completed development plans.
- [Prompts](docs/prompts/): System prompts and templates.


