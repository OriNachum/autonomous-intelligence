# Embedding Pipeline

QQ generates vector embeddings for notes, entities, and queries to enable semantic similarity search across all memory layers.

## Client Architecture

Defined in `src/qq/embeddings.py:14-177`.

### Dual Backend (`embeddings.py:42-108`)

| Backend | Description | Config |
|---------|-------------|--------|
| **TEI** (Text Embeddings Inference) | HuggingFace Docker service, fast, production-ready | `TEI_URL` (default: `http://localhost:8101/v1`) |
| **Local sentence-transformers** | Fallback for ARM64/Jetson, works offline | `EMBEDDING_MODEL` (default: `Qwen/Qwen3-Embedding-0.6B`) |

### Backend Selection (`embeddings.py:85-108`)

- If `prefer_local=True` (or `EMBEDDINGS_LOCAL=true`): Use local only, no TEI fallback
- Otherwise: Try TEI first, fall back to local on failure
- TEI connectivity check: timeout 2s, max_retries 0 (fail fast)

## Embedding Generation

### Single (`embeddings.py:110-133`)

`get_embedding(text)` --> `List[float]`

- **Local**: `SentenceTransformer.encode()` --> numpy --> tolist()
- **TEI**: OpenAI-compatible API call, returns first embedding

### Batch (`embeddings.py:135-162`)

`get_embeddings_batch(texts)` --> `List[List[float]]`

- **Local**: Vectorized `encode()` for all texts at once
- **TEI**: Single batch API request, results sorted by index
- Empty input returns `[]`

## Usage Across QQ

| Component | File | Purpose |
|-----------|------|---------|
| MongoDB notes | `mongo_store.py:66,94` | Store embeddings alongside notes |
| Deduplication | `deduplication.py:106-118` | Cosine similarity for duplicate detection |
| Neo4j entities | `neo4j_client.py:354-409` | Entity similarity search |
| Graph agent | `graph.py:222-229` | Generate entity embeddings at creation |
| Retrieval agent | `retrieval_agent.py` | Query embeddings for context assembly |
| Notes agent | `notes_agent.py:309` | Note similarity search |
| File analyzer | `analyzer.py:139-147` | Note embeddings during file internalization |

## Model

Default: **Qwen3-Embedding-0.6B** (via Qwen/Qwen3-Embedding-0.6B)

Configurable via:
- `EMBEDDING_MODEL` env var (for local backend)
- TEI service model (configured in `docker-compose.yml`)

## Docker Service

From `docker-compose.yml`:

```yaml
tei:
  image: ghcr.io/huggingface/text-embeddings-inference
  port: 8101
  model: Qwen/Qwen3-Embedding-0.6B
```
