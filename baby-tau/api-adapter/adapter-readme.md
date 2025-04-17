# API Adapter for Codex CLI

This adapter provides compatibility between OpenAI's Responses API and Chat Completions API formats,
allowing Codex CLI to work with either format.

## Using with Codex CLI

[Codex CLI](https://github.com/openai/codex) is a lightweight coding agent that runs in your terminal. 
With this adapter, you can use Codex with the locally running Ollama LLM service.

### Setup

The adapter is automatically started when you run the Codex container. To use it:

```bash
# Inside the container, Codex is already configured to use the adapter
codex "explain this codebase to me"

# You can run in different approval modes
codex --approval-mode auto-edit "refactor this function to be more readable"
codex --approval-mode full-auto "add unit tests for utils.js"
```

### Approval Modes

As described in the Codex documentation, you can control how much autonomy the agent has:

| Mode                      | What the agent may do without asking            | Still requires approval                                         |
| ------------------------- | ----------------------------------------------- | --------------------------------------------------------------- |
| **Suggest** <br>(default) | • Read any file in the repo                     | • **All** file writes/patches <br>• **All** shell/Bash commands |
| **Auto Edit**             | • Read **and** apply‑patch writes to files      | • **All** shell/Bash commands                                   |
| **Full Auto**             | • Read/write files <br>• Execute shell commands | –                                                               |

### Custom Configuration

You can create or modify configuration files in `/root/.codex/`:

- `config.yaml` - General configuration
- `instructions.md` - Custom instructions for Codex

## API Formats

The adapter supports both API formats:

- **Responses API** → `/v1/responses`
- **Chat Completions API** → `/v1/chat/completions`

For more information on the differences between these APIs, see the [OpenAI documentation](https://platform.openai.com/docs/guides/chat-completions-vs-responses).

## Testing the Adapter

You can test the adapter with:

```bash
# Test Chat Completions endpoint
curl http://localhost:8080/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{
    "model": "mistral",
    "messages": [{"role": "user", "content": "Write a haiku about AI"}]
  }'

# Test Responses endpoint
curl http://localhost:8080/v1/responses \
  -H "Content-Type: application/json" \
  -d '{
    "model": "mistral",
    "input": "Write a haiku about AI"
  }'
```
