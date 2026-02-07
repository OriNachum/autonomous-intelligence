# Agents System

QQ utilizes a modular Agent system with 8 specialized agents for tasks including general-purpose assistance, entity extraction, relationship mapping, normalization, graph linking, note-taking, file analysis, and citation alignment.

> **See also**: [Sub-Agents Documentation](./sub-agents.md) for recursive calling and parallel task execution.

## Architecture

Agents are located in `src/qq/agents/`. Each agent is a self-contained module typically consisting of:

-   **System Prompt**: A Markdown file defining the agent's persona and rules (e.g., `entity_agent.system.md`).
-   **User Prompt Template**: A Markdown file serving as a template for the user's input (e.g., `entity_agent.user.md`).
-   **Python Implementation**: The logic for the agent (e.g., `entity_agent.py`). Optional for prompt-only agents.

### Dynamic Prompt Loading

QQ employs a dynamic prompt loading mechanism via `src/qq/agents/prompt_loader.py`. This allows prompts to be modified in the Markdown files without requiring a code restart or changes to the Python source.

**Mechanism:**
1.  The `get_agent_prompts(agent_name)` function is called with the directory name of the agent.
2.  It looks for files named `{agent_name}.system.md` and `{agent_name}.user.md` within `src/qq/agents/{agent_name}/`.
3.  It returns a dictionary containing the content of these files.

### Depth-Aware Role Context

Agents receive different instructions based on their position in the delegation hierarchy:

| Depth | Role | Behavior |
|-------|------|----------|
| **0** (Root) | Coordinator | Orchestrate and delegate. Break work into subtasks, aggregate results. |
| **1-2** (Worker) | Worker | Complete assigned subtask. Can delegate if subtask has 10+ items. Be concise. |
| **3** (Leaf) | Executor | No further delegation. Do all work directly. Complete what you can, note what remains. |

## All Agents

### Default Agent

| Property | Value |
|----------|-------|
| **Directory** | `default/` |
| **Files** | `default.system.md` |
| **Purpose** | General-purpose assistant with hierarchical delegation strategy |
| **Invocation** | Direct CLI, console mode, or as default for child processes |

The main agent users interact with. Handles general questions, file operations, memory management, and task delegation. Includes the full delegation strategy for coordinating sub-agents and the citation system for source-anchored responses.

**Available Tools**: File operations (`read_file`, `list_files`, `set_directory`, `count_files`), memory tools (`memory_add`, `memory_query`, `memory_verify`, `memory_reinforce`), file analysis (`analyze_file` with optional `pattern` for batch regex-based multi-file analysis), delegation (`delegate_task`, `run_parallel_tasks`, `schedule_tasks`, `execute_scheduled_tasks`, `get_queue_status`).

---

### Entity Agent

| Property | Value |
|----------|-------|
| **Directory** | `entity_agent/` |
| **Files** | `entity_agent.system.md`, `entity_agent.user.md`, `entity_agent.py` |
| **Purpose** | Extracts entities from conversation history for the Knowledge Graph |
| **Invocation** | Called by `KnowledgeGraphAgent` pipeline (`src/qq/services/graph.py`) |

Analyzes conversation messages and extracts named entities. Binds multi-word names (e.g., "John Doe" as a single entity). Returns a JSON list of entities with name, type, and description.

**Entity Types**: Person, Concept, Topic, Location, Event, Project, Software, Organization, File, Function, Class, Configuration.

**Output Format**:
```json
[
  {"name": "Neo4j", "type": "Software", "description": "Graph database used for knowledge storage"}
]
```

---

### Relationship Agent

| Property | Value |
|----------|-------|
| **Directory** | `relationship_agent/` |
| **Files** | `relationship_agent.system.md`, `relationship_agent.user.md`, `relationship_agent.py` |
| **Purpose** | Identifies relationships between extracted entities |
| **Invocation** | Called by `KnowledgeGraphAgent` pipeline after entity extraction |

Takes extracted entities and conversation context, identifies relationships between them. Returns JSON with source, target, type, description, and confidence.

**Relationship Types**: KNOWS, RELATES_TO, USES, PART_OF, CAUSES, WORKS_ON, LOCATED_IN, DEFINED_AS, IMPORTS, EXTENDS, IMPLEMENTS, CALLS, DEPENDS_ON, CONFIGURES, CONTAINS, MENTIONS, REFERENCES, INFLUENCES, SIMILAR_TO, CONTRASTS_WITH, PRECEDES, FOLLOWS, ASSOCIATED_WITH, CO_OCCURS.

**Output Format**:
```json
[
  {"source": "QQ", "target": "Neo4j", "type": "USES", "description": "QQ uses Neo4j for knowledge graph storage", "confidence": 0.9}
]
```

---

### Normalization Agent

| Property | Value |
|----------|-------|
| **Directory** | `normalization_agent/` |
| **Files** | `normalization_agent.system.md`, `normalization_agent.py` |
| **Purpose** | Standardizes entity names, detects aliases and potential duplicates |
| **Invocation** | Called by `KnowledgeGraphAgent` pipeline after entity extraction |

Ensures entity consistency across the knowledge graph by normalizing names to canonical forms (proper case, expanded abbreviations), detecting aliases (Mike -> Michael), and identifying potential duplicates with merge confidence scores.

**Output Format**:
```json
{
  "original_name": "Dr. Smith",
  "canonical_name": "Doctor Smith",
  "aliases": ["Dr. Smith", "Smith"],
  "potential_duplicate": "John Smith",
  "merge_confidence": 0.7
}
```

---

### Graph Linking Agent

| Property | Value |
|----------|-------|
| **Directory** | `graph_linking_agent/` |
| **Files** | `graph_linking_agent.system.md`, `graph_linking_agent.user.md`, `graph_linking_agent.py` |
| **Purpose** | Finds and connects orphan entities (entities with no relationships) |
| **Invocation** | Called by `KnowledgeGraphAgent.link_orphan_entities()` |

Analyzes entities that have no relationships in the knowledge graph and suggests connections based on semantic similarity, implicit connections, hierarchical relationships, and associative patterns.

**Output Format**:
```json
[
  {"source": "OrphanEntity", "target": "ConnectedEntity", "type": "RELATES_TO", "reasoning": "Both are database technologies", "confidence": 0.8}
]
```

---

### Notes Agent

| Property | Value |
|----------|-------|
| **Directory** | `notes/` |
| **Files** | `notes.system.md`, `notes.user.md`, `notes.py` |
| **Purpose** | Summarizes conversations and manages persistent notes |
| **Invocation** | Via memory tools and `analyze_file` |
| **Persona** | Watson (Sherlock Holmes' assistant) |

Analyzes the last 20 conversation messages and extracts structured changes (additions and removals) in JSON format. Updates both `notes.md` (human-readable) and MongoDB (vector-searchable).

**Note Sections**: Key Topics, Important Facts, People & Entities, Ongoing Threads, File Knowledge.

**Output Format**:
```json
{
  "additions": [
    {"section": "Key Topics", "item": "Discussed graph database migration"}
  ],
  "removals": ["Outdated topic about old migration plan"]
}
```

---

### Analyzer Agent

| Property | Value |
|----------|-------|
| **Directory** | `analyzer_agent/` |
| **Files** | `analyzer_agent.system.md` |
| **Purpose** | Deep file analysis — extracts structured knowledge into long-term memory |
| **Invocation** | Via `analyze_file(path, focus)` tool |

Receives entire file contents and extracts structured knowledge: overview, notes, entities, and relationships. Supports focused analysis toward specific areas. Results are stored in MongoDB, notes.md, and Neo4j.

See [analyzer-agent.md](./analyzer-agent.md) for full documentation.

**Output Format**:
```json
{
  "overview": "Main orchestration module for the conversation loop",
  "notes": [
    {"section": "Key Topics", "content": "Token recovery with progressive context reduction"}
  ],
  "entities": [
    {"name": "ContextRetrievalAgent", "type": "Concept", "description": "Retrieves context before each turn"}
  ],
  "relationships": [
    {"source": "App", "target": "ContextRetrievalAgent", "type": "USES", "confidence": 0.95}
  ]
}
```

---

### Alignment Agent

| Property | Value |
|----------|-------|
| **Directory** | `alignment/` |
| **Files** | `alignment.system.md` |
| **Purpose** | Silent post-answer citation verification |
| **Invocation** | Automatic after each sourced response (when `source_registry.has_sources` is True) |

Reviews the LLM's response against the source registry to verify citation accuracy. Only surfaces when issues are found. Checks that every `[N]` citation exists and matches source content, no significant claims lack citations, and no sources are misquoted.

See [anchoring-answers-in-sources.md](./anchoring-answers-in-sources.md) for full documentation.

**Configuration**: `QQ_ALIGNMENT_ENABLED` (default: `true`).

**Output Format**:
```json
{
  "pass": false,
  "issues": [
    {"type": "missing_citation", "claim": "Neo4j uses...", "suggested_source": 4}
  ],
  "corrections": "Full corrected answer text (optional)"
}
```

## Knowledge Graph Pipeline

Four agents work together in a pipeline orchestrated by `KnowledgeGraphAgent` (`src/qq/services/graph.py`):

```
Conversation Messages
        │
        ▼
┌───────────────────┐
│   EntityAgent     │  Extract entities (Person, Concept, Topic, etc.)
└─────────┬─────────┘
          │
          ▼
┌───────────────────┐
│ RelationshipAgent │  Extract relationships between entities
└─────────┬─────────┘
          │
          ▼
┌───────────────────┐
│NormalizationAgent │  Normalize names, detect duplicates
└─────────┬─────────┘
          │
          ▼
┌───────────────────┐
│    Neo4j Store    │  Store with embeddings and metadata
└───────────────────┘

(GraphLinkingAgent runs separately to connect orphans)
```

## Using Agents

### Direct Invocation

Run QQ with a specific agent from the command line:

```bash
./qq --agent default -m "Write a sorting function"
```

### Delegation via Sub-Agents

The parent agent can delegate tasks to specialized agents at runtime:

```python
# Single task delegation
delegate_task("Analyze this file for security issues", agent="default")

# Parallel tasks
run_parallel_tasks('[
  {"task": "Analyze file1.py"},
  {"task": "Analyze file2.py"}
]')
```

See [sub-agents.md](./sub-agents.md) for full documentation on recursive calling and the task queue.

## Creating a New Agent

To add a new agent to QQ, follow these steps:

### 1. Create the Directory
Create a new directory in `src/qq/agents/` with your agent's name (e.g., `my_new_agent`).

```bash
mkdir src/qq/agents/my_new_agent
```

### 2. Add Prompt Files
Create the prompt files ensuring they match the directory name.

**`src/qq/agents/my_new_agent/my_new_agent.system.md`**:
```markdown
You are a specialized agent designed to...
```

**`src/qq/agents/my_new_agent/my_new_agent.user.md`** (optional):
```markdown
Here is the input data: {input_variable}
Please process it and return...
```

### 3. Implement the Logic (Optional)
Create a Python file for your agent (e.g., `my_new_agent.py`). Use the prompt loader to fetch your prompts.

```python
from qq.agents.prompt_loader import get_agent_prompts

class MyNewAgent:
    def __init__(self, llm_client):
        self.llm_client = llm_client

    def run(self, input_data):
        # Load prompts dynamically
        prompts = get_agent_prompts("my_new_agent")

        # Format the user prompt
        user_prompt = prompts["user"].format(input_variable=input_data)

        # Call the LLM
        response = self.llm_client.chat(
            messages=[
                {"role": "system", "content": prompts.get("system", "")},
                {"role": "user", "content": user_prompt}
            ]
        )

        return response
```

**Note**: For prompt-only agents (like `default` or `analyzer_agent`), you only need the `.system.md` file — no Python implementation required.

## Source Files

| File | Description |
|------|-------------|
| `src/qq/agents/__init__.py` | Agent loader, tool registration, `load_agent()` and `list_agents()` |
| `src/qq/agents/prompt_loader.py` | Dynamic prompt loading from `.system.md` and `.user.md` files |
| `src/qq/agents/_shared/delegation.md` | Shared delegation strategy reference for depth-aware behavior |
| `src/qq/services/graph.py` | `KnowledgeGraphAgent` — orchestrates the entity/relationship extraction pipeline |
| `src/qq/services/analyzer.py` | `FileAnalyzer` — deep file analysis and knowledge extraction |
| `src/qq/services/alignment.py` | Alignment review agent for citation verification |

## Related Documentation

- [Architecture Overview](./architecture.md)
- [Sub-Agents](./sub-agents.md): Hierarchical delegation and task queue
- [Memory System](./memory.md): How agents interact with memory
- [File Analyzer](./analyzer-agent.md): Deep file analysis details
- [Citation & Alignment](./anchoring-answers-in-sources.md): Source citation pipeline
