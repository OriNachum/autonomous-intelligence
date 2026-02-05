# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

QQ (Quick Question) is a local-first conversational AI agent with CLI and rich console interfaces. It features multi-layered memory (Notes + Knowledge Graph), specialized agents, skills system, MCP integration, and session-based parallel execution.

## Commands

```bash
# Install dependencies
uv sync

# Run (console mode)
./qq

# Run (CLI mode - one-shot)
./qq -m "your question"
./qq --agent default -m "question"

# Clear history
./qq --clear-history

# Session management (for parallel execution)
./qq -s <session-id>          # Resume a session
./qq --new-session            # Force a new session

# Utilities
./qq-memory                   # Memory status utility
./qq-backup                   # Backup/restore utility
./qq-test                     # System tests utility

# Start backend services (MongoDB, Neo4j, TEI embeddings)
docker compose up -d

# Run tests
uv run pytest
```

## CLI Options

| Flag | Type | Default | Description |
|------|------|---------|-------------|
| `-a, --agent` | string | "default" | Agent to use from agents/ folder |
| `--mode` | choice | "console" | "cli" for one-shot, "console" for REPL |
| `-m, --message` | string | None | Message to send (implies --mode cli) |
| `--clear-history` | bool | False | Clear conversation history before starting |
| `--no-color` | bool | False | Disable colored output |
| `-v, --verbose` | bool | False | Enable verbose output |
| `-s, --session` | string | None | Session ID to resume (for parallel execution) |
| `--new-session` | bool | False | Force a new session |

## Architecture

```
src/qq/
├── app.py              # Application core - orchestrates conversation loop
├── cli.py              # CLI argument parsing
├── console.py          # Rich console UI (prompt_toolkit + rich)
├── history.py          # Conversation history (JSON persistence)
├── skills.py           # YAML frontmatter skill loader
├── embeddings.py       # TEI/local embedding client
├── mcp_loader.py       # MCP server integration
├── mcp_server.py       # MCP server implementation
├── recovery.py         # Token limit recovery with context reduction
├── session.py          # Session management for parallel execution
├── errors.py           # Error definitions
├── memory_status.py    # Memory status CLI utility
├── test_systems.py     # System testing utility
├── agents/             # Specialized agents
│   ├── __init__.py     # load_agent(), list_agents() - dynamic agent loading
│   ├── prompt_loader.py # Loads .system.md and .user.md prompts
│   ├── default/        # General-purpose agent (system prompt only)
│   ├── entity_agent/   # Entity extraction from conversations
│   ├── relationship_agent/  # Relationship extraction
│   └── notes/          # Notes summarization
├── memory/             # Multi-layer notes storage system
│   ├── mongo_store.py  # MongoNotesStore with vector search
│   ├── notes.py        # NotesManager for notes.md file persistence
│   ├── core_notes.py   # Core notes functionality
│   ├── archive.py      # Notes archival system
│   ├── deduplication.py # Note deduplication logic
│   ├── importance.py   # Importance scoring for notes
│   └── notes_agent.py  # Agent for note processing
├── knowledge/          # Neo4j knowledge graph
│   └── neo4j_client.py # Neo4jClient for entity/relationship storage
├── context/            # RAG context retrieval
│   └── retrieval_agent.py
├── backup/             # Backup/restore system
│   ├── cli.py          # Backup CLI interface
│   ├── manager.py      # Backup manager
│   ├── manifest.py     # Backup manifest handling
│   ├── restore.py      # Backup restoration
│   └── stores.py       # Backup storage backends
└── services/
    ├── file_manager.py   # File ops (read with PDF/DOCX conversion)
    ├── child_process.py  # Recursive agent invocation (delegate_task, run_parallel_tasks)
    ├── task_queue.py     # Bounded task queue for batch sub-agent scheduling
    ├── graph.py          # KnowledgeGraphAgent
    └── summarizer.py     # Summary service
```

**Key patterns:**
- Agents are directories with `*.system.md` prompts (and optional `*.user.md` and `*.py` modules)
- Skills are markdown files with YAML frontmatter in `skills/` or `.agent/skills/`
- Uses Strands Agent framework for LLM tool calling
- Context injection happens before inference via retrieval_agent
- Session isolation enables parallel execution of agent instances
- Token limit recovery progressively reduces context when limits are hit

## Services (docker-compose.yml)

- **MongoDB** (27017): Notes storage with embeddings
- **Neo4j** (7474/7687): Knowledge graph (entities + relationships)
- **TEI** (8101): Text embeddings (Qwen3-Embedding-0.6B)

## Environment Variables

Key variables in `.env` (see `.env.sample`):
- `VLLM_URL` / `OPENAI_BASE_URL`: LLM endpoint
- `MODEL_ID`: Model to use
- `MONGODB_URI`, `NEO4J_URI`, `NEO4J_USER`, `NEO4J_PASSWORD`: Database connections
- `TEI_URL`, `EMBEDDING_MODEL`: Embedding service
- `HISTORY_DIR`: Conversation history location (default: `~/.qq`)
- `MEMORY_DIR`: Memory storage location

Child process / recursive calling:
- `QQ_CHILD_TIMEOUT`: Timeout for child processes in seconds (default: 300)
- `QQ_MAX_PARALLEL`: Max concurrent child processes (default: 5)
- `QQ_MAX_DEPTH`: Max recursion depth (default: 3)
- `QQ_MAX_OUTPUT`: Max output size from children in chars (default: 50000)
- `QQ_MAX_QUEUED`: Max tasks in queue per agent (default: 10)
- `QQ_NOTES_ID`: Per-agent ephemeral notes ID (internal, auto-set for children)

## MCP Configuration

External MCP servers are configured in `mcp.json` at the project root.

## Skills

Skills are markdown files with YAML frontmatter that define reusable capabilities:

- `skills/` - Global skills (e.g., `coding/SKILL.md`)
- `.agent/skills/` - Agent-specific skills (e.g., `call-qq/`, `implement/`, `plan/`, `test-on-finish/`)
