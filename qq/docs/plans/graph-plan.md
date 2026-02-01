# Graph Agent Refactoring Plan

## Goal
Decouple Entity Extraction and Relationship Extraction from the main `graph.py` into separate, focused agents. This improves modularity, maintainability, and allows for independent optimization of each step.

## Proposed Changes

### 1. New Agent Layout
We will create two new agents within `agents/graph/`:

#### **Entity Agent**
*   **File**: `agents/graph/entity_agent.py`
    *   **Class**: `EntityAgent`
    *   **Responsibility**: Takes conversation history and extracts entities.
    *   **Structure**: 
        *   `__init__(llm_client)`
        *   `extract(messages) -> List[Dict]`
*   **Prompts**:
    *   `agents/graph/entity_agent.system.md`: "You are a smart module master of Entity Extraction..."
    *   `agents/graph/entity_agent.user.md`: Contains the `ENTITY_EXTRACTION` prompt template.

#### **Relationship Agent**
*   **File**: `agents/graph/relationship_agent.py`
    *   **Class**: `RelationshipAgent`
    *   **Responsibility**: Takes conversation history + extracted entities and identifies relationships.
    *   **Structure**:
        *   `__init__(llm_client)`
        *   `extract(messages, entities) -> List[Dict]`
*   **Prompts**:
    *   `agents/graph/relationship_agent.system.md`: "You are an expert in identifying relationships between entities..."
    *   `agents/graph/relationship_agent.user.md`: Contains the `RELATIONSHIP_EXTRACTION` prompt template.

### 2. Refactor `agents/graph/graph.py`
*   **Class**: `KnowledgeGraphAgent` (or `GraphAgent`)
*   **Responsibility**: Orchestrate the process.
    *   Initialize `EntityAgent` and `RelationshipAgent`.
    *   `process_messages()`:
        1. Call `EntityAgent.extract()`
        2. Call `RelationshipAgent.extract()`
        3. Store results in Neo4j (existing logic).
*   **Cleanup**: Remove internal extraction logic and raw prompt handling from `graph.py`.

## Detailed Steps
1.  **Extract Entity Logic**: Create `entity_agent.py` and move `_clean_json_response` (or make utility) and entity extraction logic there.
2.  **Create Entity Prompts**: Create `entity_agent.system.md` and `entity_agent.user.md` from `graph.*.md`.
3.  **Extract Relationship Logic**: Create `relationship_agent.py` and move relationship extraction logic there.
4.  **Create Relationship Prompts**: Create `relationship_agent.system.md` and `relationship_agent.user.md`.
5.  **Update Graph Agent**: Rewrite `graph.py` to import and use the new classes.

## Verification
*   Ensure `GraphAgent` still initializes and runs.
*   Verify logic flow: `process_messages` calls -> `EntityAgent` -> `RelationshipAgent` -> `Neo4j`.
