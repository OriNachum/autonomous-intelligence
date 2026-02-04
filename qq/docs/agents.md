# Agents System

QQ utilizes a modular Agent system to handle specialized tasks such as entity extraction, relationship mapping, and note-taking. This document outlines the architecture, existing agents, and how to create new ones.

> **See also**: [Sub-Agents Documentation](./sub-agents.md) for recursive calling and parallel task execution.

## Architecture

Agents are located in `src/qq/agents/`. Each agent is a self-contained module typically consisting of:

-   **Python Implementation**: The logic for the agent (e.g., `entity_agent.py`).
-   **System Prompt**: A Markdown file defining the agent's persona and rules (e.g., `entity_agent.system.md`).
-   **User Prompt Template**: A Markdown file serving as a template for the user's input (e.g., `entity_agent.user.md`).

### Dynamic Prompt Loading

QQ employs a dynamic prompt loading mechanism via `src/qq/agents/prompt_loader.py`. This allows prompts to be modified in the Markdown files without requiring a code restart or changes to the Python source.

**Mechanism:**
1.  The `get_agent_prompts(agent_name)` function is called with the directory name of the agent.
2.  It looks for files named `{agent_name}.system.md` and `{agent_name}.user.md` within `src/qq/agents/{agent_name}/`.
3.  It returns a dictionary containing the content of these files.

## Existing Agents

| Agent Name | Directory | Description |
| :--- | :--- | :--- |
| **Default** | `default/` | General-purpose assistant, auto-created on first run. |
| **Entity Agent** | `entity_agent/` | Extracts entities (People, Organizations, Locations, etc.) from conversation history for the Knowledge Graph. |
| **Relationship Agent** | `relationship_agent/` | Identifies relationships between extracted entities to build connections in the Knowledge Graph. |
| **Notes Agent** | `notes/` | Summarizes conversations and manages persistent notes in MongoDB. |

## Using Agents

### Direct Invocation

Run QQ with a specific agent from the command line:

```bash
./qq --agent coder -m "Write a sorting function"
./qq --agent researcher -m "Explain quantum computing"
```

### Delegation via Sub-Agents

The parent agent can delegate tasks to specialized agents at runtime:

```python
# Single task delegation
delegate_task("Optimize this algorithm", agent="coder")

# Parallel tasks with different agents
run_parallel_tasks('[
  {"task": "Review code for bugs", "agent": "coder"},
  {"task": "Write documentation", "agent": "default"}
]')
```

See [sub-agents.md](./sub-agents.md) for full documentation on recursive calling.

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

**`src/qq/agents/my_new_agent/my_new_agent.user.md`**:
```markdown
Here is the input data: {input_variable}
Please process it and return...
```

### 3. Implement the Logic
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
