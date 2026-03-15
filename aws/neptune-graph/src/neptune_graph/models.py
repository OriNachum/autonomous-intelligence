"""Pydantic models for Neptune Graph inputs."""

from typing import Any

from pydantic import BaseModel, Field


class EntityInput(BaseModel):
    """Input for creating or updating an entity node."""

    label: str = Field(description="Node label, e.g. Person, Tool, Concept")
    name: str = Field(description="Human-readable entity name")
    properties: dict[str, Any] = Field(default_factory=dict, description="Additional node properties")


class RelationshipInput(BaseModel):
    """Input for creating a relationship between two entities."""

    from_name: str = Field(description="Source entity name")
    to_name: str = Field(description="Target entity name")
    rel_type: str = Field(description="Relationship type, e.g. USES, DEPENDS_ON")
    properties: dict[str, Any] = Field(default_factory=dict, description="Additional edge properties")


class MergeInput(BaseModel):
    """Input for merging two duplicate entities."""

    keep_name: str = Field(description="Name of the entity to keep (canonical)")
    remove_name: str = Field(description="Name of the entity to remove (duplicate)")
    strategy: str = Field(
        default="keep_primary",
        description="Merge strategy: keep_primary keeps the canonical's properties on conflict",
    )


class SplitInput(BaseModel):
    """Input for splitting an entity into two."""

    source_name: str = Field(description="Name of the entity to split from")
    new_label: str = Field(description="Label for the new entity")
    new_name: str = Field(description="Name for the new entity")
    move_properties: list[str] = Field(default_factory=list, description="Property keys to move to new entity")
    move_rel_types: list[str] = Field(default_factory=list, description="Relationship types to re-link to new entity")


class BatchEntityItem(BaseModel):
    """Single entity in a batch operation."""

    label: str
    name: str
    properties: dict[str, Any] = Field(default_factory=dict)


class BatchRelationshipItem(BaseModel):
    """Single relationship in a batch operation."""

    from_name: str
    to_name: str
    rel_type: str
    properties: dict[str, Any] = Field(default_factory=dict)


class BatchInput(BaseModel):
    """Input for batch operations."""

    entities: list[BatchEntityItem] = Field(default_factory=list)
    relationships: list[BatchRelationshipItem] = Field(default_factory=list)
