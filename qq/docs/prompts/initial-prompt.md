Write a cli / console app that uses vllm in my docker (Exists already). Saves history, reads sliding window of 20 last messages (User and model), can work as either CLI or Console app with colors.
supports prefix-caching.
Loads history on start
Has system prompt.

All agents in ./agents folder agents/<agent-name>/<agent-name>.<role>.md
wrapping code agents/<agent-name>/<agent-name>.py
Supports MCP (on start load from mcp.json the tools)
Supports agent skills (Per skill, read the skill, and if relevant, inject in conversation)

Add setup script called qq I could use to call forth the this app, or agent, from anywhere.

Use python and uv and project.toml