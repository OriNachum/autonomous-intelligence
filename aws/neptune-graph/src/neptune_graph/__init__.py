"""Neptune Graph — Python library for AWS Neptune Analytics knowledge graphs."""

from neptune_graph.config import NeptuneGraphConfig
from neptune_graph.client import NeptuneClient
from neptune_graph.models import EntityInput, RelationshipInput, MergeInput, SplitInput
from neptune_graph.operations import (
    add_entity,
    add_relationship,
    add_self_relationship,
    merge_entities,
    split_entity,
)
from neptune_graph.batch import batch_add_entities, batch_add_relationships
from neptune_graph.queries import search_entities, get_entity, get_relationships, get_summary
from neptune_graph.exceptions import NeptuneGraphError, QueryError, EntityNotFoundError

__all__ = [
    "NeptuneGraphConfig",
    "NeptuneClient",
    "EntityInput",
    "RelationshipInput",
    "MergeInput",
    "SplitInput",
    "add_entity",
    "add_relationship",
    "add_self_relationship",
    "merge_entities",
    "split_entity",
    "batch_add_entities",
    "batch_add_relationships",
    "search_entities",
    "get_entity",
    "get_relationships",
    "get_summary",
    "NeptuneGraphError",
    "QueryError",
    "EntityNotFoundError",
]
