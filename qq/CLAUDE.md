# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

QQ (Quick Question) is a local-first conversational AI agent with CLI and rich console interfaces. It features multi-layered memory (Notes + Knowledge Graph), specialized agents, skills system, and MCP integration.

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

# Memory status utility
./qq-memory

# Start backend services (MongoDB, Neo4j, TEI embeddings)
docker compose up -d

# Run tests
uv run pytest
```

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
├── agents/             # Specialized agents
│   ├── __init__.py     # load_agent() - dynamic agent loading
│   ├── prompt_loader.py # Loads .system.md and .user.md prompts
│   ├── default/        # General-purpose agent
│   ├── entity_agent/   # Entity extraction from conversations
│   ├── relationship_agent/  # Relationship extraction
│   └── notes/          # Notes summarization
├── memory/             # MongoDB-backed notes storage
│   └── mongo_store.py  # MongoNotesStore with vector search
├── knowledge/          # Neo4j knowledge graph
│   └── neo4j_client.py # Neo4jClient for entity/relationship storage
├── context/            # RAG context retrieval
│   └── retrieval_agent.py
└── services/
    ├── file_manager.py   # File ops (read with PDF/DOCX conversion)
    ├── child_process.py  # Recursive agent invocation (delegate_task, run_parallel_tasks)
    └── graph.py          # KnowledgeGraphAgent
```

**Key patterns:**
- Agents are directories with `*.system.md` and `*.user.md` files for prompts
- Skills are markdown files with YAML frontmatter in `skills/` or `.agent/skills/`
- Uses Strands Agent framework for LLM tool calling
- Context injection happens before inference via retrieval_agent

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

Child process / recursive calling:
- `QQ_CHILD_TIMEOUT`: Timeout for child processes in seconds (default: 300)
- `QQ_MAX_PARALLEL`: Max concurrent child processes (default: 5)
- `QQ_MAX_DEPTH`: Max recursion depth (default: 3)
- `QQ_MAX_OUTPUT`: Max output size from children in chars (default: 50000)

## MCP Configuration

External MCP servers are configured in `mcp.json` at the project root.
