# qq - Quick Question CLI

*Quick Question* is there to reside on your device and assist however it can.
It remembers, it can read files, MCPs and Skills.

<img width="2752" height="1536" alt="unnamed" src="https://github.com/user-attachments/assets/fe27c3c8-85fb-41a6-ac9f-a5878c4fc2e0" />

## Features

- **Colored Console UI**: Rich terminal interface with markdown rendering.
- **Conversation History**: Persistent context window with token limit recovery.
- **Agent System**: Dynamic loading of specialized agents (entity extraction, relationship extraction, notes).
- **Skills**: Automatic injection of capability sets via YAML frontmatter markdown files.
- **MCP Integration**: Support for Model Context Protocol tools.
- **Memory**: Multi-layer memory system with Notes (file + MongoDB), RAG, and GraphRAG (Neo4j) for long-term retention.
- **Parallel Execution**: Session-based isolation for concurrent agent instances.
- **Backup/Restore**: Periodic memory backups with restoration support.


## Setup

### Prerequisites
- **Python**: >= 3.10
- **uv**: Python package and project manager
- **Docker**: For memory services (MongoDB, Neo4j, TEI embeddings)

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
    cp .env.sample .env
    ```
    Key variables:
    - `VLLM_URL`: Your LLM endpoint (e.g., `http://localhost:8100/v1`)
    - `MODEL_ID`: The model name to use.
    - `MONGODB_URI`: `mongodb://localhost:27017`
    - `NEO4J_URI`: `bolt://localhost:7687`
    - `TEI_URL`: Text embeddings endpoint (e.g., `http://localhost:8101`)

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
For quick, one-off tasks without entering the console:

```bash
# Ask a quick question
./qq -m "Explain the relationship between quantum mechanics and general relativity"

# Run with a specific specialized agent
./qq --agent default -m "Summarize this file..."

# Session management for parallel execution
./qq -s <session-id>          # Resume a session
./qq --new-session            # Force a new session
```

### Utilities

```bash
./qq-memory                   # Memory status utility
./qq-backup                   # Backup/restore utility
./qq-test                     # System tests utility
```

## Documentation

- [Architecture Overview](docs/architecture.md): High-level system design.
- [Memory System](docs/memory.md): Notes, RAG, and knowledge graph details.
- [Agents](docs/agents.md): Agent system documentation.
- [Sub-Agents](docs/sub-agents.md): Child process and recursive calling.
- [Plans](docs/plans/): Active and completed development plans.


