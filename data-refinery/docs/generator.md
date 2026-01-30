# Generator Guide

Generate synthetic documents and Q&A pairs from your Neo4j knowledge graph.

## Overview

The generator queries Neo4j for entity clusters and uses vLLM to create:
- **Documents** — Coherent text incorporating multiple related entities
- **Q&A Pairs** — Question-answer training data grounded in graph knowledge

## Prerequisites

1. **Neo4j running** with imported data:
   ```bash
   docker compose up -d neo4j
   ```

2. **vLLM running**:
   ```bash
   docker compose up -d vllm
   ```

3. **Graph populated** via refinery:
   ```bash
   uv run python refinery.py -i docs/ -o output/
   cat output/import.cypher | docker exec -i data-refinery-neo4j cypher-shell -u neo4j -p refinerypass
   ```

## CLI Reference

```bash
uv run python generator.py <command> [OPTIONS]
```

### Commands

| Command | Description |
|---------|-------------|
| `documents` | Generate synthetic documents |
| `qa` | Generate question-answer pairs |

### Options

| Option | Default | Description |
|--------|---------|-------------|
| `-n, --count` | *required* | Number of items to generate |
| `-g, --guidance` | None | Steering prompt for generation |
| `-o, --output` | `output/generated` | Output directory |
| `--vllm-url` | `http://localhost:8100/v1` | vLLM endpoint |

## Document Generation

Generates coherent documents incorporating entity clusters from the graph.

```bash
# Generate 5 documents
uv run python generator.py documents --count 5

# With guidance
uv run python generator.py documents --count 10 \
  --guidance "Write as technical blog posts"
```

### How It Works

1. Queries Neo4j for a random entity
2. Fetches related entities (2-hop neighborhood)
3. Prompts LLM with entity descriptions and relationships
4. Generates document incorporating the entities naturally

### Output

Documents are saved as `doc_{n}.txt`:

```
output/generated/
├── doc_0.txt
├── doc_1.txt
└── doc_2.txt
```

## Q&A Generation

Creates question-answer pairs grounded in graph knowledge.

```bash
# Generate 20 Q&A pairs
uv run python generator.py qa --count 20

# With guidance
uv run python generator.py qa --count 50 \
  --guidance "Focus on beginner-level questions about ML concepts"
```

### How It Works

1. Picks a random entity with relationships
2. Includes entity description + connected entities
3. Prompts LLM to create a question answerable from the context
4. Returns both question and grounded answer

### Output

Q&A pairs are saved as `qa_pairs.json`:

```json
[
  {
    "question": "What is the relationship between neural networks and deep learning?",
    "answer": "Neural networks are the foundation of deep learning...",
    "source_entity": "neural_networks"
  }
]
```

## Guidance Examples

Guidance steers generation style, difficulty, and focus:

```bash
# Technical style
--guidance "Write in formal academic style"

# Difficulty level
--guidance "Create challenging questions for ML experts"

# Topic focus
--guidance "Focus on computer vision topics"

# Format
--guidance "Format as flashcards with short answers"

# Combined
--guidance "Write beginner-friendly explanations using analogies"
```

## Custom Endpoint

```bash
uv run python generator.py qa --count 10 \
  --vllm-url http://gpu-server:8100/v1
```

## Programmatic Usage

```python
from src.generator_app import GeneratorConfig, QAGenerator, DocumentGenerator

config = GeneratorConfig(
    vllm_url="http://localhost:8100/v1",
    output_dir="output/generated"
)

# Generate Q&A
qa_gen = QAGenerator(config)
pairs = qa_gen.generate_qa_pairs(count=10, guidance="Focus on basics")
qa_gen.close()

# Generate documents
doc_gen = DocumentGenerator(config)
docs = doc_gen.generate_documents(count=5)
doc_gen.close()
```
