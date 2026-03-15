"""Exception hierarchy for Neptune Graph operations."""


class NeptuneGraphError(Exception):
    """Base exception for all Neptune Graph errors."""


class QueryError(NeptuneGraphError):
    """Error executing an openCypher query."""

    def __init__(self, message: str, query: str | None = None):
        self.query = query
        super().__init__(message)


class EntityNotFoundError(NeptuneGraphError):
    """Entity not found in the graph."""

    def __init__(self, identifier: str):
        self.identifier = identifier
        super().__init__(f"Entity not found: {identifier}")
