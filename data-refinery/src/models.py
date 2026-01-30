"""Data models for entity and relationship extraction."""
from typing import List, Optional
from pydantic import BaseModel, Field


class Entity(BaseModel):
    """An extracted entity from the document."""
    id: str = Field(description="Unique identifier for this entity")
    name: str = Field(description="Name of the entity")
    type: str = Field(description="Type: name, concept, feature, or location")
    description: str = Field(description="Brief description of the entity")
    source_page: int = Field(description="Page number where entity was found")
    embedding: Optional[List[float]] = Field(default=None, description="Optional embedding vector")
    
    def to_cypher_id(self) -> str:
        """Generate a safe Cypher-compatible ID."""
        return self.id.replace("-", "_").replace(" ", "_")


class Relationship(BaseModel):
    """A relationship between two entities."""
    source_entity_id: str = Field(description="ID of the source entity")
    target_entity_id: str = Field(description="ID of the target entity")
    type: str = Field(description="Type of relationship")
    description: str = Field(description="Description of the relationship")
    source_page: int = Field(description="Page number where relationship was found")


class EntityExtractionResult(BaseModel):
    """Result from entity extraction call."""
    entities: List[Entity] = Field(default_factory=list)


class RelationshipExtractionResult(BaseModel):
    """Result from relationship extraction call."""
    relationships: List[Relationship] = Field(default_factory=list)
    continue_extraction: bool = Field(
        default=False,
        description="Whether to continue extracting more relationships"
    )


class WindowExtractionResult(BaseModel):
    """Complete extraction result for a sliding window."""
    document_name: str
    start_page: int
    end_page: int
    entities: List[Entity] = Field(default_factory=list)
    relationships: List[Relationship] = Field(default_factory=list)
    
    def to_dict(self) -> dict:
        """Convert to dictionary for JSON serialization."""
        return {
            "document_name": self.document_name,
            "start_page": self.start_page,
            "end_page": self.end_page,
            "entities": [e.model_dump() for e in self.entities],
            "relationships": [r.model_dump() for r in self.relationships],
        }
