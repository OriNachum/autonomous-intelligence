# Architecture

QQ is designed as a local-first, modular AI agent that interacts through a CLI or a rich console interface. It leverages a "Host" concept to manage interactions, memory, and specialized capabilities through Agents, Skills, and MCP (Model Context Protocol).

## High-Level Overview

```mermaid
graph TD
    User[User] -->|Input| CLI[CLI / Console]
    CLI --> App[Application Loop]
    
    subgraph Core "Core System"
        App --> Memory[Memory System]
        App --> Tools[Tool Manager]
        App --> LLM[LLM Client]
    end
    
    subgraph MemoryLayer "Memory Layer"
        Memory --> Mongo[(MongoDB - Notes)]
        Memory --> Neo4j[(Neo4j - Graph)]
        Memory --> Vector[Vector Embeddings]
    end
    
    subgraph Capabilities "Capabilities"
        Tools --> Agents[Agents]
        Tools --> Skills[Skills]
        Tools --> MCP[MCP Servers]
    end
    
    LLM -->|Generation| App
    App -->|Output| User
```

## Key Components

### 1. Interface Layer
- **CLI (`src/qq/cli.py`)**: Entry point for command-line arguments and one-shot commands.
- **Console (`src/qq/console.py`)**: A rich, interactive terminal UI powered by `rich` and `prompt_toolkit`. It supports history navigation, multi-line input, and slash commands.

### 2. Application Core (`src/qq/app.py`)
orchestrates the conversation loop. It:
- Captures user input.
- Retrieves relevant context from Memory.
- Selects appropriate Tools (Agents/Skills).
- Sends the prompt to the LLM (vLLM).
- Renders the response.

### 3. Memory System (`src/qq/memory/`, `src/qq/knowledge/`)
QQ persists information to maintain context across sessions:
- **Notes (`memory/notes.md`)**: A summarized running log of conversations and facts, stored in MongoDB with vector embeddings for semantic retrieval.
- **Knowledge Graph (Neo4j)**: Structured data representing entities and relationships extracted from conversations.
- **Context Retrieval**: Fetches relevant notes and graph connections before generating a response.

### 4. Agent System (`src/qq/agents/`)
Agents are specialized modules for specific tasks. For detailed documentation, see [agents.md](./agents.md).
- **Structure**: Each agent resides in its own directory (e.g., `src/qq/agents/coder/`).
- **Definition**: Defined by `*.system.md` (System Prompt) and `*.user.md` (User Prompt template).
- **Dynamic Loading**: Prompts are loaded at runtime, allowing for easy modification without code changes.

### 5. Skills System (`skills/`, `src/qq/skills.py`)
Skills are "folders of instructions" that extend the agent's capabilities.
- **Location**: Store in `skills/` (root) or `.agent/skills/`.
- **Format**: A skill is a directory containing a `SKILL.md` with instructions and metadata.
- **Injection**: Relevant skills are dynamically injected into the LLM context based on the user's request.

### 6. MCP Integration (`src/qq/mcp_loader.py`)
QQ supports the Model Context Protocol (MCP) to connect with external tools and data sources.
- **Configuration**: Defined in `mcp.json`.
- **Functionality**: Allows QQ to call tools exposed by external servers (e.g., file reading, web search).

## Data Flow

1.  **Input**: User types a message.
2.  **Context Construction**:
    *   Retrieve recent conversation history.
    *   Search Memory (MongoDB) for relevant notes.
    *   Query Knowledge Graph (Neo4j) for related entities.
3.  **Prompt Assembly**: Combine System Prompt + Context + User Input + Available Tools (Skills/MCP/Agents).
4.  **Inference**: Send Payload to LLM (e.g., vLLM).
5.  **Execution**:
    *   If LLM requests a tool call, execute the tool (Edit File, Run Command, etc.) and feed output back.
    *   If LLM produces text, stream it to the user.
6.  **Persistence**:
    *   Save message to history.
    *   Background agents process the interaction to update Notes and Knowledge Graph.
