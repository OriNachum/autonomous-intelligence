# Configuration Reference

All service endpoints are configured in `config.json` in the skill directory.

## config.json Fields

### `llm` — Language Model

| Field | Default | Description |
|-------|---------|-------------|
| `base_url` | `http://localhost:8100/v1` | OpenAI-compatible API endpoint |
| `api_key` | `NO_NEED` | API key (set for OpenAI/cloud providers) |
| `model_id` | `nvidia/NVIDIA-Nemotron-3-Nano-30B-A3B-FP8` | Model identifier |

Works with any OpenAI-compatible endpoint: vLLM, OpenAI API, Ollama, LiteLLM, etc.

### `embeddings` — Text Embeddings

| Field | Default | Description |
|-------|---------|-------------|
| `base_url` | `http://localhost:8101/v1` | TEI or OpenAI-compatible embeddings endpoint |
| `model` | `Qwen/Qwen3-Embedding-0.6B` | Embedding model name |
| `prefer_local` | `false` | Use local sentence-transformers instead of TEI |

Backend priority: TEI service > OpenAI-compatible endpoint > local sentence-transformers.

### `mongodb` — Notes Store

| Field | Default | Description |
|-------|---------|-------------|
| `uri` | `mongodb://localhost:27017` | MongoDB connection URI |
| `database` | `qq_memory` | Database name |
| `collection` | `notes` | Collection name |

### `neo4j` — Knowledge Graph

| Field | Default | Description |
|-------|---------|-------------|
| `uri` | `bolt://localhost:7687` | Neo4j Bolt protocol URI |
| `user` | `neo4j` | Username |
| `password` | `refinerypass` | Password |

### `memory` — File Storage

| Field | Default | Description |
|-------|---------|-------------|
| `memory_dir` | `./memory` | Directory for notes.md, core.md, archive.jsonl |

### `docker_compose_path`

| Field | Default | Description |
|-------|---------|-------------|
| `docker_compose_path` | `./docker-compose.yml` | Path to compose file for service management |

## Environment Variable Overrides

Env vars override `config.json` values when set:

| Env Var | Config Path |
|---------|------------|
| `VLLM_URL` | `llm.base_url` |
| `OPENAI_BASE_URL` | `llm.base_url` |
| `OPENAI_API_KEY` | `llm.api_key` |
| `MODEL_ID` | `llm.model_id` |
| `TEI_URL` | `embeddings.base_url` |
| `EMBEDDING_MODEL` | `embeddings.model` |
| `EMBEDDINGS_LOCAL` | `embeddings.prefer_local` (set to `true`) |
| `MONGODB_URI` | `mongodb.uri` |
| `NEO4J_URI` | `neo4j.uri` |
| `NEO4J_USER` | `neo4j.user` |
| `NEO4J_PASSWORD` | `neo4j.password` |
| `MEMORY_DIR` | `memory.memory_dir` |

## Resolution Order

1. Environment variables (highest priority)
2. `config.json` values
3. Hardcoded defaults (lowest priority)

## OpenAI API Setup

To use OpenAI API instead of local vLLM:

```bash
python scripts/setup_openai.py \
  --base-url https://api.openai.com/v1 \
  --api-key sk-your-key-here \
  --model gpt-4o
```

Or edit `config.json` directly:

```json
{
  "llm": {
    "base_url": "https://api.openai.com/v1",
    "api_key": "sk-your-key-here",
    "model_id": "gpt-4o"
  }
}
```

## Partial Setup

Each service is independently optional. Configure only what you need:

- **MongoDB only**: Notes with vector search, no knowledge graph
- **Neo4j only**: Knowledge graph, no persistent notes
- **No services**: File-based notes.md and core.md only
- **All services**: Full memory system with RAG, graph, and embeddings
