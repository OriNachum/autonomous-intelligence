# vLLM LLM Server

OpenAI-compatible inference server powered by [vLLM](https://docs.vllm.ai/).

| Property | Value |
|----------|-------|
| Image | `nvcr.io/nvidia/vllm:25.12.post1-py3` |
| Default model | `nvidia/NVIDIA-Nemotron-3-Nano-30B-A3B-FP8` |
| Port | `8000` |
| Health endpoint | `GET /health` |
| API endpoint | `POST /v1/chat/completions` |

Key server flags (set in `docker-compose.yaml`):

```
--gpu-memory-utilization 0.60
--max-num-seqs 8
--tensor-parallel-size 1
--max-model-len 131072
--enable-chunked-prefill
--kv-cache-dtype fp8
--enable-prefix-caching
--trust-remote-code
--enable-auto-tool-choice
--tool-call-parser qwen3_coder
```

---

## Reasoning Modes

**Reasoning behavior is controlled at inference time (in the curl / API request), not by restarting vLLM.**

### For Qwen3 Models

Qwen3 models support a native `enable_thinking` flag via `chat_template_kwargs`:

| Mode | `enable_thinking` | System prompt | Temperature | Latency | Use case |
|------|-------------------|---------------|-------------|---------|----------|
| Deep reasoning | `true` | _(none or open-ended)_ | 0.6 | High | Complex analysis, math, coding |
| Medium reasoning | `true` | `"Be concise. Think briefly."` | 0.7 | Medium | Balanced quality + speed |
| No reasoning | `false` | `"Answer directly."` | 0.8 | Low | Chat, Q&A, simple tasks |

### For Nemotron (Default Model)

Nemotron doesn't have a native thinking mode. Control reasoning via system prompt + temperature:

| Mode | System prompt | Temperature | Latency | Use case |
|------|---------------|-------------|---------|----------|
| Deep reasoning | `"Think step by step. Show your reasoning."` | 0.3 | High | Complex analysis |
| Medium reasoning | `"Be thorough but concise."` | 0.5 | Medium | Balanced |
| No reasoning | `"Answer directly and concisely."` | 0.8 | Low | Chat, simple tasks |

---

## Curl Examples

### Basic chat completion (no reasoning — Nemotron)

```bash
curl http://localhost:8000/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{
    "model": "nvidia/NVIDIA-Nemotron-3-Nano-30B-A3B-FP8",
    "messages": [
      {"role": "system", "content": "Answer directly and concisely."},
      {"role": "user", "content": "What is the capital of France?"}
    ],
    "temperature": 0.8,
    "stream": false
  }'
```

### Streaming chat completion (no reasoning — Nemotron)

```bash
curl http://localhost:8000/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{
    "model": "nvidia/NVIDIA-Nemotron-3-Nano-30B-A3B-FP8",
    "messages": [
      {"role": "system", "content": "Answer directly and concisely."},
      {"role": "user", "content": "Explain Docker in one sentence."}
    ],
    "temperature": 0.8,
    "stream": true
  }'
```

### Deep reasoning (Qwen3 — thinking enabled)

```bash
curl http://localhost:8000/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{
    "model": "Qwen/Qwen3-30B-A3B",
    "messages": [
      {"role": "user", "content": "Prove that the square root of 2 is irrational."}
    ],
    "temperature": 0.6,
    "stream": true,
    "chat_template_kwargs": {"enable_thinking": true}
  }'
```

### No reasoning (Qwen3 — thinking disabled)

```bash
curl http://localhost:8000/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{
    "model": "Qwen/Qwen3-30B-A3B",
    "messages": [
      {"role": "user", "content": "What is 2 + 2?"}
    ],
    "temperature": 0.8,
    "stream": false,
    "chat_template_kwargs": {"enable_thinking": false}
  }'
```

### Deep reasoning (Nemotron — step-by-step prompt)

```bash
curl http://localhost:8000/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{
    "model": "nvidia/NVIDIA-Nemotron-3-Nano-30B-A3B-FP8",
    "messages": [
      {"role": "system", "content": "Think step by step. Show your full reasoning before giving the final answer."},
      {"role": "user", "content": "A train leaves at 9am going 60mph. Another leaves at 10am going 80mph. When does the second catch up?"}
    ],
    "temperature": 0.3,
    "stream": true
  }'
```

---

## Tool Calling

Tool calling is enabled via server flags:

```
--enable-auto-tool-choice
--tool-call-parser qwen3_coder
```

Example with tools:

```bash
curl http://localhost:8000/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{
    "model": "nvidia/NVIDIA-Nemotron-3-Nano-30B-A3B-FP8",
    "messages": [
      {"role": "user", "content": "What is the weather in Tel Aviv?"}
    ],
    "tools": [
      {
        "type": "function",
        "function": {
          "name": "get_weather",
          "description": "Get current weather for a location",
          "parameters": {
            "type": "object",
            "properties": {
              "location": {"type": "string", "description": "City name"}
            },
            "required": ["location"]
          }
        }
      }
    ],
    "tool_choice": "auto",
    "stream": false
  }'
```

Change the parser via `VLLM_TOOL_CALL_PARSER` env var (default: `qwen3_coder`).

---

## How the Bridge Calls vLLM

The realtime-api bridge (`llm_client.py`) sends this payload shape:

```json
{
  "model": "<OPENAI_MODEL>",
  "messages": [
    {"role": "system", "content": "<session instructions>"},
    {"role": "user", "content": "<transcribed text>"},
    {"role": "assistant", "content": "<previous response>"}
  ],
  "stream": true,
  "temperature": 0.8,
  "max_tokens": null
}
```

The bridge does **not** pass `chat_template_kwargs`, so:
- For Qwen3: `enable_thinking` cannot be controlled through the bridge — call vLLM directly
- For Nemotron: reasoning is influenced via `temperature` and `instructions` (system prompt) in the `session.update` event

---

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `VLLM_MODEL` | `nvidia/NVIDIA-Nemotron-3-Nano-30B-A3B-FP8` | HuggingFace model ID to serve |
| `VLLM_PORT` | `8000` | HTTP port |
| `VLLM_GPU_MEMORY` | `0.60` | Fraction of GPU memory for KV cache (`gpu-memory-utilization`) |
| `VLLM_MAX_NUM_SEQS` | `8` | Max concurrent sequences |
| `VLLM_MAX_MODEL_LEN` | `131072` | Max context length in tokens |
| `VLLM_TOOL_CALL_PARSER` | `qwen3_coder` | Tool call parser (e.g. `qwen3_coder`, `hermes`) |
| `HF_TOKEN` | _(required)_ | HuggingFace token for gated models |
| `OPENAI_BASE_URL` | `http://vllm-llm:8000` | URL the bridge uses to reach vLLM |
| `OPENAI_API_KEY` | `EMPTY` | API key for vLLM (any value works, vLLM doesn't enforce) |
| `OPENAI_MODEL` | `nvidia/NVIDIA-Nemotron-3-Nano-30B-A3B-FP8` | Model name the bridge sends in requests |

---

## Swapping Models

1. Edit `.env`:
   ```bash
   VLLM_MODEL=Qwen/Qwen3-30B-A3B
   OPENAI_MODEL=Qwen/Qwen3-30B-A3B
   VLLM_TOOL_CALL_PARSER=qwen3_coder
   ```

2. Restart the vLLM container (it will download and serve the new model):
   ```bash
   docker compose up -d vllm-llm
   ```

3. The bridge (`realtime-api`) picks up `OPENAI_MODEL` automatically — restart it too if already running:
   ```bash
   docker compose restart realtime-api
   ```

Popular models for DGX Spark (128 GB unified memory):

| Model | Size | `VLLM_GPU_MEMORY` | Notes |
|-------|------|--------------------|-------|
| `nvidia/NVIDIA-Nemotron-3-Nano-30B-A3B-FP8` | ~15 GB | 0.60 | Default, fast MoE |
| `Qwen/Qwen3-30B-A3B` | ~18 GB | 0.60 | Native thinking mode |
| `Qwen/Qwen3-32B` | ~35 GB | 0.70 | Dense, higher quality |
