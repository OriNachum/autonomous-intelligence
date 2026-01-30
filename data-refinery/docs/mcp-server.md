# MCP Server Guide

Access your Neo4j knowledge graph via the Model Context Protocol (MCP).

## Overview

Data Refinery includes a FastMCP server that exposes your graph as MCP tools, enabling AI agents to query entities and relationships.

## Running the Server

```bash
uv run python -m src.mcp_server
```

The server uses stdio transport by default (standard MCP protocol).

### Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `NEO4J_URI` | `bolt://localhost:7687` | Neo4j connection URI |
| `NEO4J_USER` | `neo4j` | Database user |
| `NEO4J_PASSWORD` | `refinerypass` | Database password |

## Available Tools

### `get_graph_schema`

Returns the schema of your graph — entity types, relationship types, and counts.

```json
{
  "entity_types": ["Concept", "Name", "Feature", "Location"],
  "relationship_types": ["RELATES_TO", "INCLUDES", "LOCATED_IN"],
  "entity_counts": {
    "Concept": 150,
    "Name": 45,
    "Feature": 32
  }
}
```

### `query_entities`

Search for entities by type or name pattern.

**Parameters:**
| Name | Type | Description |
|------|------|-------------|
| `entity_type` | string | Filter by type (Name, Concept, Feature, Location) |
| `name_pattern` | string | Case-insensitive name search |
| `limit` | int | Max results (default: 20) |

**Example:**
```python
query_entities(entity_type="Concept", name_pattern="learning", limit=10)
```

### `get_entity_by_id`

Retrieve a specific entity by its ID.

**Parameters:**
| Name | Type | Description |
|------|------|-------------|
| `entity_id` | string | Unique entity ID |

### `get_related_entities`

Find entities connected to a given entity.

**Parameters:**
| Name | Type | Description |
|------|------|-------------|
| `entity_id` | string | Source entity ID |
| `relationship_type` | string | Filter by relationship type |
| `direction` | string | `"in"`, `"out"`, or `"both"` |
| `limit` | int | Max results (default: 20) |

**Example:**
```python
get_related_entities(
    entity_id="machine_learning",
    relationship_type="INCLUDES",
    direction="out"
)
```

### `query_relationships`

Query relationships with filters.

**Parameters:**
| Name | Type | Description |
|------|------|-------------|
| `source_type` | string | Filter source entity type |
| `target_type` | string | Filter target entity type |
| `relationship_type` | string | Filter relationship type |
| `limit` | int | Max results (default: 20) |

### `run_cypher`

Execute raw Cypher queries (read-only).

**Parameters:**
| Name | Type | Description |
|------|------|-------------|
| `query` | string | Cypher query |
| `limit` | int | Safety limit (default: 50) |

**Security:** Write operations (CREATE, MERGE, DELETE, SET) are blocked.

**Example:**
```python
run_cypher("MATCH (n:Concept)-[:INCLUDES]->(m) RETURN n.name, m.name")
```

## Integration Examples

### With Claude Desktop

Add to your `claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "data-refinery": {
      "command": "uv",
      "args": ["run", "python", "-m", "src.mcp_server"],
      "cwd": "/path/to/data-refinery",
      "env": {
        "NEO4J_URI": "bolt://localhost:7687",
        "NEO4J_USER": "neo4j",
        "NEO4J_PASSWORD": "refinerypass"
      }
    }
  }
}
```

### With Cline / VS Code

Configure in your MCP settings to connect to the stdio server.

## Direct Python Usage

```python
from src.mcp_server import get_client, query_entities, get_related_entities

# Query entities
results = query_entities(entity_type="Concept", limit=10)

# Get relationships
related = get_related_entities(entity_id="neural_networks", direction="both")
```
