"""Generator application using Neo4j graph for document and Q&A generation."""
import os
import json
import random
from typing import List, Dict, Any, Optional
from pathlib import Path
from dataclasses import dataclass

from openai import OpenAI


@dataclass
class GeneratorConfig:
    """Configuration for the generator."""
    vllm_url: str = "http://localhost:8100/v1"
    model: str = os.getenv("MODEL_ID", "nvidia/NVIDIA-Nemotron-3-Nano-30B-A3B-FP8")
    neo4j_uri: str = os.getenv("NEO4J_URI", "bolt://localhost:7687")
    neo4j_user: str = os.getenv("NEO4J_USER", "neo4j")
    neo4j_password: str = os.getenv("NEO4J_PASSWORD", "refinerypass")
    output_dir: str = "output/generated"


class Neo4jGraphClient:
    """Simple Neo4j client for querying graph data."""
    
    def __init__(self, uri: str, user: str, password: str):
        from neo4j import GraphDatabase
        self.driver = GraphDatabase.driver(uri, auth=(user, password))
    
    def close(self):
        self.driver.close()
    
    def execute(self, query: str, parameters: dict = None) -> List[Dict[str, Any]]:
        """Execute a Cypher query."""
        with self.driver.session() as session:
            result = session.run(query, parameters or {})
            return [record.data() for record in result]
    
    def get_random_entities(self, count: int = 5) -> List[Dict[str, Any]]:
        """Get random entities from the graph."""
        query = """
            MATCH (n)
            WHERE n.name IS NOT NULL AND n.description IS NOT NULL
            WITH n, rand() as r
            ORDER BY r
            LIMIT $count
            RETURN n.id as id, n.name as name, labels(n)[0] as type, n.description as description
        """
        return self.execute(query, {"count": count})
    
    def get_related_entities(self, entity_id: str, limit: int = 5) -> List[Dict[str, Any]]:
        """Get entities related to a given entity."""
        query = """
            MATCH (n {id: $entity_id})-[r]-(m)
            RETURN m.id as id, m.name as name, labels(m)[0] as type, 
                   m.description as description, type(r) as relationship
            LIMIT $limit
        """
        return self.execute(query, {"entity_id": entity_id, "limit": limit})
    
    def get_entity_cluster(self, count: int = 3) -> List[Dict[str, Any]]:
        """Get a cluster of related entities for coherent generation."""
        # First get a random entity
        seed_entities = self.get_random_entities(1)
        if not seed_entities:
            return []
        
        seed = seed_entities[0]
        entities = [seed]
        
        # Get related entities
        related = self.get_related_entities(seed["id"], count - 1)
        entities.extend(related)
        
        return entities[:count]


class DocumentGenerator:
    """Generate synthetic documents from graph knowledge."""
    
    DOCUMENT_PROMPT = """Based on the following entities and their relationships from a knowledge graph, 
write a cohesive, informative document that naturally incorporates this information.

ENTITIES:
{entities}

{guidance_section}

Write a well-structured document (2-4 paragraphs) that:
1. Naturally discusses the entities and their relationships
2. Provides context and explanation
3. Reads like genuine educational or informational content
4. Does not explicitly mention that it's based on a knowledge graph

Document:"""

    def __init__(self, config: GeneratorConfig):
        self.config = config
        self.llm = OpenAI(base_url=config.vllm_url, api_key="not-needed")
        self.graph = Neo4jGraphClient(
            config.neo4j_uri,
            config.neo4j_user,
            config.neo4j_password,
        )
    
    def _format_entities(self, entities: List[Dict[str, Any]]) -> str:
        """Format entities for prompt."""
        lines = []
        for e in entities:
            rel_info = f" (relationship: {e.get('relationship', 'N/A')})" if 'relationship' in e else ""
            lines.append(f"- {e['name']} ({e.get('type', 'Unknown')}): {e.get('description', 'No description')}{rel_info}")
        return "\n".join(lines)
    
    def generate_document(self, guidance: Optional[str] = None) -> str:
        """Generate a single document."""
        # Get entity cluster for coherent content
        entities = self.graph.get_entity_cluster(random.randint(3, 6))
        
        if not entities:
            return ""
        
        guidance_section = f"GUIDANCE: {guidance}" if guidance else ""
        
        prompt = self.DOCUMENT_PROMPT.format(
            entities=self._format_entities(entities),
            guidance_section=guidance_section,
        )
        
        response = self.llm.chat.completions.create(
            model=self.config.model,
            messages=[
                {"role": "system", "content": "You are a technical writer creating educational content."},
                {"role": "user", "content": prompt},
            ],
            temperature=0.7,
            max_tokens=1024,
        )
        
        return response.choices[0].message.content.strip()
    
    def generate_documents(self, count: int, guidance: Optional[str] = None) -> List[str]:
        """Generate multiple documents."""
        documents = []
        for _ in range(count):
            doc = self.generate_document(guidance)
            if doc:
                documents.append(doc)
        return documents
    
    def close(self):
        self.graph.close()


class QAGenerator:
    """Generate Q&A pairs from graph knowledge."""
    
    QA_PROMPT = """Based on the following entity and its relationships from a knowledge graph,
create a high-quality question-answer pair for training or evaluation purposes.

ENTITY:
- Name: {name}
- Type: {type}
- Description: {description}

RELATED ENTITIES:
{related}

{guidance_section}

Generate a question that can be answered using this information, and provide a comprehensive answer.
Format your response as JSON:
{{"question": "...", "answer": "..."}}

JSON:"""

    def __init__(self, config: GeneratorConfig):
        self.config = config
        self.llm = OpenAI(base_url=config.vllm_url, api_key="not-needed")
        self.graph = Neo4jGraphClient(
            config.neo4j_uri,
            config.neo4j_user,
            config.neo4j_password,
        )
    
    def generate_qa_pair(self, guidance: Optional[str] = None) -> Optional[Dict[str, str]]:
        """Generate a single Q&A pair."""
        # Get a random entity
        entities = self.graph.get_random_entities(1)
        if not entities:
            return None
        
        entity = entities[0]
        
        # Get related entities for context
        related = self.graph.get_related_entities(entity["id"], 3)
        related_text = "\n".join(
            f"- {r['name']}: {r.get('description', 'No description')} (via {r.get('relationship', 'unknown')})"
            for r in related
        ) or "None found"
        
        guidance_section = f"GUIDANCE: {guidance}" if guidance else ""
        
        prompt = self.QA_PROMPT.format(
            name=entity["name"],
            type=entity.get("type", "Unknown"),
            description=entity.get("description", "No description"),
            related=related_text,
            guidance_section=guidance_section,
        )
        
        response = self.llm.chat.completions.create(
            model=self.config.model,
            messages=[
                {"role": "system", "content": "You are creating training data for AI models. Respond only with valid JSON."},
                {"role": "user", "content": prompt},
            ],
            temperature=0.7,
            max_tokens=512,
        )
        
        content = response.choices[0].message.content.strip()
        
        # Parse JSON (handle potential markdown wrapping)
        if content.startswith("```"):
            lines = content.split("\n")
            content = "\n".join(lines[1:-1] if lines[-1].strip() == "```" else lines[1:])
        
        try:
            return json.loads(content)
        except json.JSONDecodeError:
            return None
    
    def generate_qa_pairs(self, count: int, guidance: Optional[str] = None) -> List[Dict[str, str]]:
        """Generate multiple Q&A pairs."""
        pairs = []
        attempts = 0
        max_attempts = count * 2  # Allow some failures
        
        while len(pairs) < count and attempts < max_attempts:
            pair = self.generate_qa_pair(guidance)
            if pair:
                pairs.append(pair)
            attempts += 1
        
        return pairs
    
    def close(self):
        self.graph.close()


def save_documents(documents: List[str], output_dir: Path):
    """Save generated documents to files."""
    output_dir.mkdir(parents=True, exist_ok=True)
    
    for i, doc in enumerate(documents, 1):
        filepath = output_dir / f"document_{i:04d}.txt"
        with open(filepath, "w") as f:
            f.write(doc)
        print(f"  Saved: {filepath}")


def save_qa_pairs(pairs: List[Dict[str, str]], output_dir: Path):
    """Save Q&A pairs to a JSON file."""
    output_dir.mkdir(parents=True, exist_ok=True)
    
    filepath = output_dir / "qa_pairs.json"
    with open(filepath, "w") as f:
        json.dump(pairs, f, indent=2, ensure_ascii=False)
    print(f"  Saved: {filepath}")
