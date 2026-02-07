# Architecture

QQ is designed as a local-first, modular AI agent that interacts through a CLI or a rich console interface. It leverages a multi-layered memory system, hierarchical task delegation, source-anchored citations, and specialized agents for structured knowledge extraction.

## High-Level Overview

```mermaid
graph TD
    User[User] -->|Input| CLI[CLI / Console]
    CLI --> App[Application Loop]

    subgraph Core "Core System"
        App --> Recovery[Token Recovery]
        App --> Context[Context Retrieval]
        App --> Memory[Memory System]
        App --> Tools[Tool Manager]
        App --> LLM[LLM Client]
    end

    subgraph MemoryLayer "Memory Layer"
        Memory --> CoreNotes[Core Notes - core.md]
        Memory --> Mongo[(MongoDB - Notes + RAG)]
        Memory --> Neo4j[(Neo4j - Knowledge Graph)]
        Memory --> Vector[TEI Embeddings]
        Memory --> Ephemeral[Ephemeral Notes - notes.*.md]
    end

    subgraph Capabilities "Capabilities"
        Tools --> Agents[Agents]
        Tools --> Skills[Skills]
        Tools --> MCP[MCP Servers]
        Tools --> SubAgents[Sub-Agents]
        Tools --> Analyzer[File Analyzer]
        Tools --> MemTools[Memory Tools]
    end

    subgraph SubAgentLayer "Sub-Agent Execution"
        SubAgents --> ChildProcess[ChildProcess Service]
        ChildProcess --> TaskQueue[Task Queue]
        TaskQueue --> Child1[Child QQ #1]
        TaskQueue --> Child2[Child QQ #2]
        TaskQueue --> ChildN[Child QQ #N]
    end

    subgraph PostResponse "Post-Response"
        App --> Alignment[Alignment Review]
        App --> Sources[Source Footer]
    end

    LLM -->|Generation| App
    App -->|Output| User
```

## Key Components

### 1. Interface Layer
- **CLI (`src/qq/cli.py`)**: Entry point for command-line arguments and one-shot commands.
- **Console (`src/qq/console.py`)**: A rich, interactive terminal UI powered by `rich` and `prompt_toolkit`. Supports history navigation, multi-line input, and slash commands.

### 2. Application Core (`src/qq/app.py`)
Orchestrates the conversation loop:
- Captures user input.
- Creates per-turn `SourceRegistry` for citation tracking.
- Retrieves relevant context from Memory via `ContextRetrievalAgent`.
- Selects appropriate Tools (Agents/Skills).
- Sends the prompt to the LLM.
- Runs alignment review on sourced responses.
- Appends source footer and renders the response.

### 3. Memory System (`src/qq/memory/`, `src/qq/knowledge/`)
QQ persists information across four layers to maintain context across sessions:

| Layer | Storage | Source | Purpose |
|-------|---------|--------|---------|
| **Core Notes** | `core.md` file | `src/qq/memory/core_notes.py` | Protected essential info (identity, projects, relationships, system) — never auto-forgotten |
| **Flat Notes (RAG)** | MongoDB + `notes.md` | `src/qq/memory/mongo_store.py`, `notes.py` | Vector-searchable notes with importance scoring and time decay |
| **Knowledge Graph** | Neo4j | `src/qq/knowledge/neo4j_client.py` | 12 entity types, 22 relationship types with embeddings |
| **Ephemeral Notes** | `notes.{id}.md` files | `src/qq/memory/notes.py` | Per-agent working memory for sub-tasks, auto-cleaned |

See [memory.md](./memory.md) for detailed architecture.

### 4. Context Retrieval (`src/qq/context/retrieval_agent.py`)
Before each LLM call, gathers relevant context:
- Core notes (always included)
- Working notes via MongoDB vector search
- Knowledge graph entities via Neo4j embedding similarity
- Assigns sequential `[N]` indices via `SourceRegistry` for citations
- Items below `QQ_CITE_THRESHOLD` (default 0.3) are excluded

### 5. Agent System (`src/qq/agents/`)
Eight specialized agents handle distinct tasks. For detailed documentation, see [agents.md](./agents.md).

| Agent | Purpose | Invocation |
|-------|---------|------------|
| **Default** | General-purpose assistant with delegation | Direct / CLI |
| **Entity Agent** | Entity extraction from conversations | KnowledgeGraphAgent pipeline |
| **Relationship Agent** | Relationship extraction between entities | KnowledgeGraphAgent pipeline |
| **Normalization Agent** | Entity name standardization and dedup | KnowledgeGraphAgent pipeline |
| **Graph Linking Agent** | Connects orphan entities | KnowledgeGraphAgent pipeline |
| **Notes Agent** | Conversation summarization, note management | Memory tools / analyze_file |
| **Analyzer Agent** | Deep file analysis and knowledge extraction | `analyze_file` tool |
| **Alignment Agent** | Post-answer citation verification | Automatic (silent) |

**Structure**: Each agent resides in its own directory with `*.system.md` (system prompt) and optional `*.user.md` (user prompt template) and `*.py` (Python implementation).

**Dynamic Loading**: Prompts are loaded at runtime via `prompt_loader.py`, allowing modification without code changes.

### 6. Sub-Agent System (`src/qq/services/child_process.py`, `task_queue.py`)
QQ can spawn child instances of itself to handle delegated tasks. For detailed documentation, see [sub-agents.md](./sub-agents.md).

- **Task Delegation**: `delegate_task` spawns a child agent for a single task
- **Parallel Execution**: `run_parallel_tasks` runs multiple tasks concurrently
- **Queue-Based Scheduling**: `schedule_tasks` + `execute_scheduled_tasks` for priority-ordered batch processing
- **Capacity**: 10 tasks per queue × 3 depth levels = 1,000 items per hierarchical request
- **Session Isolation**: Each child runs with `--new-session` to prevent state pollution
- **Ephemeral Notes**: Each child gets its own `notes.{id}.md` working memory
- **Ancestry Tracking**: `QQ_ANCESTOR_REQUESTS` preserves full lineage from root to leaf
- **Safety**: Recursion depth limits, timeouts, output truncation, bounded queues

### 7. Skills System (`skills/`, `src/qq/skills.py`)
Skills extend the agent's capabilities via markdown files with YAML frontmatter.

| Skill | Location | Purpose |
|-------|----------|---------|
| `coding` | `skills/` | Enhanced coding assistance |
| `plan` | `.agent/skills/` | Structured plan generation |
| `implement` | `.agent/skills/` | Plan executor |
| `test-on-finish` | `.agent/skills/` | Automated testing after implementation |
| `call-qq` | `.agent/skills/` | CLI invocation patterns |
| `neo4j-query` | `.agent/skills/` | Neo4j Cypher query assistance |
| `mongodb-query` | `.agent/skills/` | MongoDB query assistance |

**Injection**: Relevant skills are dynamically injected into the LLM context based on trigger keywords.

### 8. MCP Integration (`src/qq/mcp_loader.py`, `src/qq/mcp_server.py`)
QQ supports the Model Context Protocol (MCP) to connect with external tools and data sources.
- **Configuration**: Defined in `mcp.json` at the project root.
- **MCPLoader**: Connects to stdio-based MCP servers, lists tools, converts to OpenAI format.
- **MCP Server**: FastMCP server exposing `read_file` tool via MCP protocol.

### 9. Source Provenance (`src/qq/memory/source.py`)
Every memory item tracks its origin. See [source-metadata.md](./source-metadata.md).
- SHA-256 checksums for file content verification
- Git metadata (repo, branch, commit, author)
- Session and agent IDs
- Source history for audit trails

### 10. Citation & Alignment (`src/qq/services/source_registry.py`, `alignment.py`)
Responses are anchored to their sources. See [anchoring-answers-in-sources.md](./anchoring-answers-in-sources.md).
- `SourceRegistry` assigns `[N]` indices to retrieved context
- LLM uses footnote-style citations in responses
- Silent `AlignmentAgent` verifies citations post-answer
- Source footer appended with indexed source list

### 11. Token Recovery (`src/qq/recovery.py`)
Progressive context reduction when token limits are hit:
- Window sizes: 20 → 10 → 5 → 2 → 0 (current message only)
- Max retries: 4
- Overflow classification: minor, major, catastrophic, unknown
- Catastrophic overflow (tool output too large) triggers immediate failure with guidance

### 12. File Analyzer (`src/qq/services/analyzer.py`)
Deep file internalization that extracts structured knowledge. See [analyzer-agent.md](./analyzer-agent.md).
- Reads entire file (bypasses sliding window)
- Extracts overview, notes, entities, relationships via LLM
- Stores in MongoDB, notes.md, and Neo4j
- Re-analysis detection via SHA-256 checksums
- Large file auto-splitting at ~30k chars

## Data Flow

1.  **Input**: User types a message.
2.  **Source Registry**: Per-turn `SourceRegistry` created for citation tracking.
3.  **Context Construction**:
    *   Retrieve recent conversation history.
    *   Search Memory (MongoDB) for relevant notes via vector similarity.
    *   Query Knowledge Graph (Neo4j) for related entities via embedding similarity.
    *   Load Core Notes (always included).
    *   Assign `[N]` indices to all retrieved sources.
4.  **Prompt Assembly**: Combine System Prompt + Context (with `[N]` markers) + User Input + Available Tools (Skills/MCP/Agents).
5.  **Inference**: Send payload to LLM.
6.  **Execution**:
    *   If LLM requests a tool call, execute the tool and feed output back. Tool results (memory queries, file reads) are registered as additional sources.
    *   If LLM produces text, stream it to the user.
7.  **Alignment Review**: Silent agent checks citation accuracy (only when sources were used).
8.  **Source Footer**: Append indexed source list to response.
9.  **Persistence**:
    *   Save message to conversation history.
    *   Memory stored only via explicit tool calls (`memory_add`, `memory_reinforce`, `analyze_file`).

## Source Files

```
src/qq/
├── app.py                          # Main orchestration loop
├── cli.py                          # CLI argument parsing
├── console.py                      # Rich terminal UI
├── history.py                      # Conversation persistence
├── session.py                      # Session management
├── recovery.py                     # Token limit recovery
├── skills.py                       # Skill loader
├── embeddings.py                   # TEI embedding client
├── mcp_loader.py                   # MCP server integration
├── mcp_server.py                   # MCP server implementation
├── agents/
│   ├── __init__.py                 # Agent/tool loader and registration
│   ├── prompt_loader.py            # Dynamic prompt loading
│   ├── _shared/delegation.md       # Delegation strategy reference
│   ├── default/                    # General-purpose agent
│   ├── entity_agent/               # Entity extraction
│   ├── relationship_agent/         # Relationship extraction
│   ├── normalization_agent/        # Entity normalization
│   ├── graph_linking_agent/        # Orphan entity linking
│   ├── notes/                      # Notes management (Watson persona)
│   ├── analyzer_agent/             # File analysis prompts
│   └── alignment/                  # Citation alignment review
├── memory/
│   ├── mongo_store.py              # MongoDB notes store with vectors
│   ├── notes.py                    # Notes manager (main + ephemeral)
│   ├── core_notes.py               # Core notes (protected, never forgotten)
│   ├── archive.py                  # Notes archival system
│   ├── deduplication.py            # SHA-256 + semantic dedup
│   ├── importance.py               # Importance scoring with decay
│   ├── source.py                   # SourceRecord and provenance
│   └── notes_agent.py              # Notes extraction agent
├── knowledge/
│   └── neo4j_client.py             # Neo4j client for entities/relationships
├── context/
│   └── retrieval_agent.py          # Context retrieval with source indexing
├── services/
│   ├── file_manager.py             # File operations (PDF/DOCX conversion)
│   ├── child_process.py            # Sub-agent spawning and management
│   ├── task_queue.py               # Bounded priority task queue
│   ├── graph.py                    # KnowledgeGraphAgent pipeline
│   ├── analyzer.py                 # FileAnalyzer for deep analysis
│   ├── alignment.py                # Alignment review agent
│   ├── source_registry.py          # Per-turn source citation registry
│   ├── memory_tools.py             # Memory tool creation
│   ├── summarizer.py               # Output summarization
│   └── output_guard.py             # Output size protection
└── backup/
    ├── cli.py                      # Backup CLI interface
    ├── manager.py                  # Backup manager
    ├── manifest.py                 # Backup manifest handling
    ├── restore.py                  # Backup restoration
    └── stores.py                   # Backup storage backends
```

## Related Documentation

- [Agents](./agents.md): All 8 agents and creation guide
- [Sub-Agents](./sub-agents.md): Hierarchical delegation and task queue
- [Memory System](./memory.md): Multi-layer memory architecture
- [Source Metadata](./source-metadata.md): Provenance tracking
- [Citation & Alignment](./anchoring-answers-in-sources.md): Source citation pipeline
- [File Analyzer](./analyzer-agent.md): Deep file internalization
- [Task Queue](./task-queue.md): Priority-based scheduling internals
