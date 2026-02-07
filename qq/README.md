# qq - Quick Question CLI

*Quick Question* is a local-first conversational AI agent with hierarchical task delegation, multi-layered memory, and knowledge graph integration. It resides on your device and assists however it can — remembering context across sessions, reading files, delegating to specialized sub-agents, and scaling to process up to 1,000 items through recursive task decomposition.

<img width="2752" height="1536" alt="unnamed" src="https://github.com/user-attachments/assets/fe27c3c8-85fb-41a6-ac9f-a5878c4fc2e0" />

## Features

- **Rich Console UI**: Interactive terminal interface with markdown rendering, syntax highlighting, and slash commands.
- **Conversation History**: Persistent context window with automatic token limit recovery (progressive context reduction).
- **Agent System**: 8 specialized agents — general-purpose, entity extraction, relationship extraction, normalization, graph linking, notes, file analysis, and alignment review.
- **Hierarchical Sub-Agents**: Recursive task delegation with up to 1,000 concurrent items (10 tasks x 3 depth levels), priority-based scheduling, and ephemeral per-agent memory.
- **Skills**: Capability injection via YAML frontmatter markdown files (coding, planning, implementation, testing, database queries).
- **Multi-Layer Memory**: Core notes (protected, never forgotten), flat notes (MongoDB + vector search), knowledge graph (Neo4j entities & relationships), and ephemeral notes (per-agent working memory).
- **Source Provenance**: Every memory item tracks its origin with SHA-256 checksums, git metadata, and citation pipelines.
- **Citation & Alignment**: Footnote-style `[N]` source citations with silent post-answer alignment review.
- **File Analysis**: Deep file internalization that extracts structured knowledge into long-term memory.
- **MCP Integration**: Model Context Protocol for external tool connectivity.
- **Session Isolation**: Parallel execution with independent session state.
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

### CLI Options

| Flag | Type | Default | Description |
|------|------|---------|-------------|
| `-a, --agent` | string | `"default"` | Agent to use from agents/ folder |
| `--mode` | choice | `"console"` | `"cli"` for one-shot, `"console"` for REPL |
| `-m, --message` | string | None | Message to send (implies `--mode cli`) |
| `--clear-history` | bool | False | Clear conversation history before starting |
| `--no-color` | bool | False | Disable colored output |
| `-v, --verbose` | bool | False | Enable verbose output |
| `-s, --session` | string | None | Session ID to resume |
| `--new-session` | bool | False | Force a new session |

### Utilities

```bash
./qq-memory                   # Memory status utility
./qq-backup                   # Backup/restore utility
./qq-test                     # System tests utility
```

## Agents

QQ includes 8 specialized agents that work together:

| Agent | Directory | Purpose |
|-------|-----------|---------|
| **Default** | `default/` | General-purpose assistant with hierarchical delegation strategy |
| **Entity Agent** | `entity_agent/` | Extracts entities (Person, Concept, Topic, etc.) from conversations |
| **Relationship Agent** | `relationship_agent/` | Identifies relationships between extracted entities |
| **Normalization Agent** | `normalization_agent/` | Standardizes entity names, detects aliases and duplicates |
| **Graph Linking Agent** | `graph_linking_agent/` | Connects orphan entities with missing relationships |
| **Notes Agent** | `notes/` | Summarizes conversations and manages persistent notes (Watson persona) |
| **Analyzer Agent** | `analyzer_agent/` | Deep file analysis — extracts notes, entities, relationships into memory |
| **Alignment Agent** | `alignment/` | Silent post-answer citation verification |

### Sub-Agent Hierarchy

Agents can delegate tasks to child agents, forming a 3-level hierarchy:

```
Root Agent (depth 0) — Coordinator
├── Up to 10 tasks queued
├── Child Agent (depth 1) — Worker
│   ├── Up to 10 tasks queued
│   └── Leaf Agent (depth 2) — Executor
│       └── Up to 10 tasks queued (no further delegation)
└── ...
```

**Capacity model**: `10 tasks × 10 children × 10 grandchildren = 1,000 items processable per request`

Each child runs in an isolated session with its own ephemeral notes file for working memory. Core notes (`core.md`) remain shared across all agents, providing consistent identity and context.

### Delegation Tools

| Tool | Use Case |
|------|----------|
| `delegate_task(task, agent)` | Single focused task to a specific agent |
| `run_parallel_tasks(tasks_json)` | 2-10 independent tasks concurrently |
| `schedule_tasks(tasks_json)` | Queue 10+ tasks with priority ordering |
| `execute_scheduled_tasks()` | Run all queued tasks |
| `get_queue_status()` | Check capacity before delegating |

## Memory System

QQ uses a four-layer memory architecture:

| Layer | Storage | Purpose | Shared? |
|-------|---------|---------|---------|
| **Core Notes** | `core.md` file | Protected identity, projects, relationships, system info — never forgotten | Yes (all agents) |
| **Flat Notes (RAG)** | MongoDB + `notes.md` | Vector-searchable notes with importance scoring and decay | Root agent |
| **Knowledge Graph** | Neo4j | Structured entities and relationships with 12 entity types and 22 relationship types | Yes (all agents) |
| **Ephemeral Notes** | `notes.{id}.md` | Per-agent working memory for sub-tasks, auto-cleaned | No (per-agent) |

### Memory Tools

| Tool | Description |
|------|-------------|
| `memory_add(content, category, importance)` | Store new information |
| `memory_query(query, category, limit)` | Search memory via vector similarity |
| `memory_verify(content)` | Check for conflicts with existing knowledge |
| `memory_reinforce(entity_name, evidence)` | Strengthen existing knowledge |
| `analyze_file(path, focus)` | Deep file internalization into all memory layers |

### Context Retrieval Pipeline

Before each response, the `ContextRetrievalAgent` gathers relevant context:
1. Core notes (always included)
2. Working notes (MongoDB vector search)
3. Knowledge graph entities (Neo4j embedding similarity)
4. Source indexing with `[N]` markers for citations

## Services (docker-compose.yml)

| Service | Port | Purpose |
|---------|------|---------|
| MongoDB | 27017 | Notes storage with vector embeddings |
| Neo4j | 7474/7687 | Knowledge graph (entities + relationships) |
| TEI | 8101 | Text embeddings (Qwen3-Embedding-0.6B) |

## Configuration

### Environment Variables

**LLM**
- `VLLM_URL` / `OPENAI_BASE_URL`: LLM endpoint
- `MODEL_ID` / `MODEL_NAME`: Model to use
- `OPENAI_API_KEY`: API key (default: `"EMPTY"`)

**Memory Services**
- `MONGODB_URI`: MongoDB connection (default: `mongodb://localhost:27017`)
- `NEO4J_URI`: Neo4j Bolt URI (default: `bolt://localhost:7687`)
- `NEO4J_USER` / `NEO4J_PASSWORD`: Neo4j credentials
- `TEI_URL`: Text embeddings endpoint (default: `http://localhost:8101`)
- `EMBEDDING_MODEL`: Embedding model name

**Storage**
- `HISTORY_DIR`: Conversation history location (default: `~/.qq`)
- `MEMORY_DIR`: Memory storage location

**Sub-Agent Limits**
- `QQ_CHILD_TIMEOUT`: Timeout per child process in seconds (default: `300`)
- `QQ_MAX_PARALLEL`: Max concurrent child processes (default: `5`)
- `QQ_MAX_DEPTH`: Max recursion depth (default: `3`)
- `QQ_MAX_OUTPUT`: Max output size from children in chars (default: `50000`)
- `QQ_MAX_QUEUED`: Max tasks in queue per agent (default: `10`)

**Features**
- `QQ_ALIGNMENT_ENABLED`: Enable citation alignment review (default: `true`)
- `QQ_CITE_THRESHOLD`: Minimum relevance score for source indexing (default: `0.3`)

## Skills

Skills extend agent capabilities via markdown files with YAML frontmatter:

| Skill | Location | Purpose |
|-------|----------|---------|
| `coding` | `skills/` | Enhanced coding assistance |
| `plan` | `.agent/skills/` | Structured plan generation |
| `implement` | `.agent/skills/` | Plan executor |
| `test-on-finish` | `.agent/skills/` | Automated testing after implementation |
| `call-qq` | `.agent/skills/` | CLI invocation patterns |
| `neo4j-query` | `.agent/skills/` | Neo4j Cypher query assistance |
| `mongodb-query` | `.agent/skills/` | MongoDB query assistance |

## Documentation

- [Architecture Overview](docs/architecture.md): High-level system design and data flow.
- [Agents](docs/agents.md): Agent system, all 8 agents, and creation guide.
- [Sub-Agents](docs/sub-agents.md): Hierarchical delegation, task queue, and capacity model.
- [Task Queue](docs/task-queue.md): Priority-based scheduling internals.
- [Memory System](docs/memory.md): Multi-layer memory architecture overview.
  - [Flat Notes (MongoDB RAG)](docs/memory-flat.md): Vector-searchable notes storage.
  - [Knowledge Graph (Neo4j)](docs/memory-graph.md): Entity and relationship schema.
  - [Core Notes](docs/memory-notes-core.md): Protected essential information.
  - [Ephemeral Notes](docs/memory-notes-ephemeral.md): Per-agent working memory.
- [File Analyzer](docs/analyzer-agent.md): Deep file internalization.
- [Source Metadata](docs/source-metadata.md): Provenance tracking and checksums.
- [Citation & Alignment](docs/anchoring-answers-in-sources.md): Source citation pipeline.
- [Plans](docs/plans/): Active and completed development plans.
