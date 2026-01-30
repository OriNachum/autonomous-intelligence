# Getting Started

Complete setup guide for Data Refinery.

## Prerequisites

- **Docker** with GPU support (NVIDIA Container Toolkit)
- **Python 3.10+**
- **Hugging Face account** with access to [Nemotron-3](https://huggingface.co/nvidia/NVIDIA-Nemotron-3-Nano-30B-A3B-FP8)

## 1. Environment Setup

```bash
# Clone the repository
git clone <repo-url>
cd data-refinery

# Copy environment template
cp .env.sample .env
```

Edit `.env` and add your Hugging Face token:

```bash
HF_TOKEN=hf_your_token_here
MODEL_ID=nvidia/NVIDIA-Nemotron-3-Nano-30B-A3B-FP8
```

## 2. Install Dependencies

```bash
./init_env.sh
```

This uses [uv](https://github.com/astral-sh/uv) to manage dependencies. If uv isn't installed, the script installs it automatically.

## 3. Start Services

### All services (vLLM, Neo4j, TEI)

```bash
docker compose up -d
```

### Just what you need

```bash
# Neo4j only (for Cypher imports)
docker compose up -d neo4j

# vLLM only (for extraction)
docker compose up -d vllm

# TEI only (for embeddings)
docker compose up -d tei
```

### Verify services

| Service | Health Check |
|---------|--------------|
| vLLM | `curl http://localhost:8100/health` |
| Neo4j | `curl http://localhost:7474` |
| TEI | `curl http://localhost:8101/health` |

## 4. First Extraction

```bash
# Process a single PDF
uv run python refinery.py --input your-document.pdf --output output/

# Or process a directory
uv run python refinery.py --input docs/ --output output/
```

**Output:**
- `output/*.json` — Extracted entities and relationships per window
- `output/import.cypher` — Neo4j import script

## 5. Import to Neo4j

```bash
cat output/import.cypher | docker exec -i data-refinery-neo4j cypher-shell -u neo4j -p refinerypass
```

Browse your graph at [http://localhost:7474](http://localhost:7474) (credentials: `neo4j/refinerypass`).

## 6. Generate Training Data

```bash
# Generate synthetic documents
uv run python generator.py documents --count 5 -o output/generated

# Generate Q&A pairs
uv run python generator.py qa --count 20 -o output/generated
```

## Next Steps

- **[Refinery Guide](refinery.md)** — Deep dive into extraction options
- **[Generator Guide](generator.md)** — Fine-tune generation with guidance
- **[MCP Server](mcp-server.md)** — Query graph via MCP protocol
