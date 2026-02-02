# QQ Memory Architecture

The `qq` agent employs a sophisticated multi-layered memory architecture designed to maintain long-term context, structure knowledge, and provide relevant information during interactions. This system is composed of three main components: **Notes**, **Knowledge Graph**, and **RAG (Retrieval Augmented Generation)**.

## 1. Notes System
The Notes system is responsible for maintaining a human-readable summary of conversations and key facts, while also identifying these facts for vector-based retrieval.

*   **Agent**: `NotesAgent`
*   **Source**: `src/qq/agents/notes/notes.py`
*   **Storage**:
    *   **File**: `notes.md` (Human-readable, plain text)
    *   **Database**: MongoDB (Vector store)

### Technical Details
*   **Extraction**: The agent analyzes the last 20 messages of a conversation. It uses a specialized prompt (`notes.user.md`) to extract additions and removals to the current notes state.
*   **Schema (MongoDB)**:
    *   Database: `qq_memory`
    *   Collection: `notes`
    *   Fields:
        *   `note_id`: SHA-256 hash of the content (unique identifier).
        *   `content`: The text content of the note.
        *   `section`: The logical section or topic (e.g., "Key Topics").
        *   `embedding`: Vector embedding of the content (used for search).
        *   `updated_at`: Timestamp of last update.
*   **Implementation**: `MongoNotesStore` (`src/qq/memory/mongo_store.py`) handles CRUD operations and vector similarity search. currently implementing a manual cosine similarity calculation for portability, with potential for MongoDB Atlas Vector Search scaling.

## 2. Knowledge Graph
The Knowledge Graph structures information into entities and their relationships, allowing the agent to understand complex connections between concepts.

*   **Agent**: `KnowledgeGraphAgent`
*   **Source**: `src/qq/services/graph.py`
*   **Storage**: Neo4j Graph Database

### Technical Details
*   **Extraction**:
    1.  **Entity Extraction**: `EntityAgent` identifies concepts, people, and locations.
    2.  **Relationship Extraction**: `RelationshipAgent` identifies connections between the extracted entities.
*   **Schema (Neo4j)**:
    *   **Nodes (Entities)**:
        *   `Label`: The entity type (e.g., `Person`, `Concept`, `Topic`).
        *   `name`: Unique identifier.
        *   `description`: Contextual description.
        *   `embedding`: Vector representation of "name: description".
    *   **Edges (Relationships)**:
        *   `Type`: The nature of the relationship (e.g., `RELATES_TO`, `KNOWS`).
        *   `description`: Details about the relationship.
*   **Implementation**: `Neo4jClient` (`src/qq/knowledge/neo4j_client.py`) manages graph operations. It supports both Cypher queries for traversal and embedding-based lookup for entity discovery.

## 3. RAG (Retrieval Augmented Generation)
The Context Retrieval system bridges the storage layers (Notes & Graph) with the active conversation, injecting relevant context into the model's working memory.

*   **Agent**: `ContextRetrievalAgent`
*   **Source**: `src/qq/context/retrieval_agent.py`

### Retrieval Flow
1.  **Query**: The agent receives the user's current input message.
2.  **Parallel Search**:
    *   **Notes**: Queries MongoDB for notes with high cosine similarity to the input.
    *   **Graph**: Queries Neo4j for entities with high embedding similarity to the input.
3.  **Filtering**: Results include a relevance score. Items with a score below a threshold (e.g., `0.3`) are discarded.
4.  **Formatting**: Valid results are formatted into a markdown block:
    *   `**Relevant Memory Notes**`: List of matching note contents.
    *   `**Related Knowledge**`: List of matching entities with their descriptions and types.
5.  **Injection**: This formatted block is injected into the System Prompt before the main instruction, ensuring the LLM is aware of the context *before* generating a response.

## Integration
All three components are initialized in the main application entry point (`src/qq/app.py`).
*   **Initialization**: `NotesAgent`, `KnowledgeGraphAgent`, and `ContextRetrievalAgent` are instantiated with shared `EmbeddingClient` and `LLMClient` instances.
*   **Cycle**:
    1.  **Pre-Response**: `ContextRetrievalAgent` injects context into the prompt.
    2.  **Response**: The model generates a reply.
    3.  **Post-Response**: `NotesAgent` and `KnowledgeGraphAgent` process the new interaction history in the background to update their respective stores.
