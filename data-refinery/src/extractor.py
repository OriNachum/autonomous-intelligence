"""Entity and relationship extractor using vLLM with prefix caching."""
import json
import uuid
from typing import List, Optional

from openai import OpenAI
from tenacity import retry, stop_after_attempt, wait_exponential

from .models import (
    Entity,
    EntityExtractionResult,
    Relationship,
    RelationshipExtractionResult,
    WindowExtractionResult,
)
from .document_processor import SlidingWindow


# Prompts for extraction
ENTITY_EXTRACTION_PROMPT = """You are an expert at extracting structured information from documents.

Analyze the following document content and extract all important entities.
Entities should be one of these types:
- **name**: People, organizations, brands
- **concept**: Ideas, theories, methodologies, abstract concepts
- **feature**: Product features, capabilities, characteristics
- **location**: Physical or virtual locations, regions, places

For each entity, provide:
- id: A unique snake_case identifier
- name: The entity name as it appears
- type: One of [name, concept, feature, location]
- description: A brief description (1-2 sentences)
- source_page: The page number where it was found

DOCUMENT CONTENT:
{content}

Respond with a JSON object containing an "entities" array. Example:
{{
  "entities": [
    {{"id": "machine_learning", "name": "Machine Learning", "type": "concept", "description": "A field of AI focused on learning from data.", "source_page": 1}}
  ]
}}

Extract all significant entities. Be thorough but avoid duplicates."""


RELATIONSHIP_EXTRACTION_PROMPT = """You are an expert at extracting relationships between entities from documents.

Given the document content and a list of identified entities, extract relationships between them.
Each relationship should describe how two entities are connected.

DOCUMENT CONTENT:
{content}

IDENTIFIED ENTITIES:
{entities}

RELATIONSHIPS FOUND SO FAR:
{relationships}

For each NEW relationship (not already listed above), provide:
- source_entity_id: ID of the source entity
- target_entity_id: ID of the target entity  
- type: The type of relationship (e.g., "uses", "contains", "is_part_of", "created_by")
- description: Brief description of the relationship
- source_page: Page number where the relationship is evident

Also indicate if there are MORE relationships to extract.

Respond with a JSON object:
{{
  "relationships": [
    {{"source_entity_id": "entity_a", "target_entity_id": "entity_b", "type": "uses", "description": "Entity A uses Entity B for processing.", "source_page": 1}}
  ],
  "continue_extraction": true
}}

Set "continue_extraction" to true ONLY if you are confident there are more meaningful relationships not yet captured. Otherwise set to false."""


class Extractor:
    """Extract entities and relationships using vLLM."""
    
    def __init__(
        self,
        vllm_url: str = "http://localhost:8000/v1",
        model: str = "nvidia/NVIDIA-Nemotron-3-Nano-30B-A3B-FP8",
        max_relationship_iterations: int = 5,
        temperature: float = 0.1,
    ):
        """
        Initialize the extractor.
        
        Args:
            vllm_url: URL of the vLLM OpenAI-compatible API
            model: Model name to use
            max_relationship_iterations: Max iterations for relationship extraction
            temperature: Sampling temperature
        """
        self.client = OpenAI(base_url=vllm_url, api_key="not-needed")
        self.model = model
        self.max_relationship_iterations = max_relationship_iterations
        self.temperature = temperature
    
    @retry(stop=stop_after_attempt(3), wait=wait_exponential(min=1, max=10))
    def _call_llm(self, messages: list, response_format: dict = None) -> str:
        """Make an API call to vLLM with retry logic."""
        kwargs = {
            "model": self.model,
            "messages": messages,
            "temperature": self.temperature,
            "max_tokens": 4096,
        }
        if response_format:
            kwargs["response_format"] = response_format
            
        response = self.client.chat.completions.create(**kwargs)
        return response.choices[0].message.content
    
    def _parse_json_response(self, response: str) -> dict:
        """Parse JSON from LLM response, handling markdown code blocks."""
        # Strip markdown code blocks if present
        response = response.strip()
        if response.startswith("```"):
            lines = response.split("\n")
            # Remove first and last lines (code block markers)
            lines = lines[1:-1] if lines[-1].strip() == "```" else lines[1:]
            response = "\n".join(lines)
        
        return json.loads(response)
    
    def extract_entities(self, window: SlidingWindow) -> List[Entity]:
        """
        Extract entities from a sliding window.
        
        This is Step 1 of the extraction process.
        Uses prefix caching by keeping the content prompt consistent.
        
        Args:
            window: The sliding window to process
            
        Returns:
            List of extracted entities
        """
        prompt = ENTITY_EXTRACTION_PROMPT.format(content=window.combined_text)
        
        messages = [
            {"role": "system", "content": "You are a precise entity extraction assistant. Always respond with valid JSON."},
            {"role": "user", "content": prompt},
        ]
        
        response = self._call_llm(messages)
        
        try:
            data = self._parse_json_response(response)
            result = EntityExtractionResult(**data)
            return result.entities
        except (json.JSONDecodeError, ValueError) as e:
            print(f"Warning: Failed to parse entity response: {e}")
            return []
    
    def extract_relationships(
        self,
        window: SlidingWindow,
        entities: List[Entity],
        existing_relationships: List[Relationship] = None,
    ) -> RelationshipExtractionResult:
        """
        Extract relationships from a sliding window.
        
        This is Step 2+ of the extraction process.
        Leverages prefix caching by keeping content prefix consistent.
        
        Args:
            window: The sliding window to process
            entities: Previously extracted entities
            existing_relationships: Relationships found in prior iterations
            
        Returns:
            RelationshipExtractionResult with new relationships and continue flag
        """
        existing_relationships = existing_relationships or []
        
        # Format entities for prompt
        entities_text = "\n".join(
            f"- {e.id}: {e.name} ({e.type}) - {e.description}"
            for e in entities
        )
        
        # Format existing relationships
        relationships_text = "None yet." if not existing_relationships else "\n".join(
            f"- {r.source_entity_id} --[{r.type}]--> {r.target_entity_id}: {r.description}"
            for r in existing_relationships
        )
        
        prompt = RELATIONSHIP_EXTRACTION_PROMPT.format(
            content=window.combined_text,
            entities=entities_text,
            relationships=relationships_text,
        )
        
        messages = [
            {"role": "system", "content": "You are a precise relationship extraction assistant. Always respond with valid JSON."},
            {"role": "user", "content": prompt},
        ]
        
        response = self._call_llm(messages)
        
        try:
            data = self._parse_json_response(response)
            return RelationshipExtractionResult(**data)
        except (json.JSONDecodeError, ValueError) as e:
            print(f"Warning: Failed to parse relationship response: {e}")
            return RelationshipExtractionResult(relationships=[], continue_extraction=False)
    
    def extract_all(self, window: SlidingWindow) -> WindowExtractionResult:
        """
        Perform complete extraction for a sliding window.
        
        Process:
        1. Extract entities (single call)
        2. Iteratively extract relationships until model says stop
        
        Uses prefix caching: the window content is the same prefix for all calls,
        allowing vLLM to cache and reuse KV computations.
        
        Args:
            window: The sliding window to process
            
        Returns:
            Complete extraction result
        """
        # Step 1: Extract entities
        entities = self.extract_entities(window)
        
        if not entities:
            return WindowExtractionResult(
                document_name=window.document_name,
                start_page=window.start_page,
                end_page=window.end_page,
                entities=[],
                relationships=[],
            )
        
        # Step 2+: Iteratively extract relationships
        all_relationships = []
        iteration = 0
        
        while iteration < self.max_relationship_iterations:
            result = self.extract_relationships(window, entities, all_relationships)
            
            # Add new relationships
            all_relationships.extend(result.relationships)
            iteration += 1
            
            # Check if we should continue
            if not result.continue_extraction or not result.relationships:
                break
        
        return WindowExtractionResult(
            document_name=window.document_name,
            start_page=window.start_page,
            end_page=window.end_page,
            entities=entities,
            relationships=all_relationships,
        )
