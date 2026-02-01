# Agents Infrastructure Plan

## Goal
Establish a robust infrastructure for agents under `src/qq/agents` and implement a dynamic prompt loading mechanism.

## Infrastructure Location
- All agent code and resources shall reside under `src/qq/agents`.
- Each agent should have its own subdirectory (e.g., `src/qq/agents/some_agent/`).

## Prompt Management
- **Requirement**: A method that accepts an agent identifier (string) and retrieves the corresponding prompts.
- **Mechanism**:
    - The method will locate the agent's directory based on the identifier.
    - It will read the system prompt from `{agent_name}.system.md` and the user prompt from `{agent_name}.user.md`.
    - This ensures prompts are managed in external Markdown files, which are easier to edit and version.

## Execution Flow
- **Before every agent execution**:
    - Call the prompt loading method.
    - Inject the loaded prompts into the agent's context.
    - This guarantees that the agent effectively uses the most up-to-date prompts from the file system without requiring a restart or code redeployment.
