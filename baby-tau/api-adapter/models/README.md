# Models Directory

## Overview

The `models` directory contains Pydantic data models that define the structure of requests and responses in the API adapter. These models provide type safety, validation, and documentation for the API.

## Directory Structure

```
models/
├── __init__.py       # Exports models for easy importing
└── requests.py       # Request data model definitions
```

## Model Components

### requests.py

This file defines the data models for the Responses API requests, including:

- `ResponseRequest`: The main request model for the Responses API
- `ResponseMessage`: Model for message objects within a response
- `ResponseContent`: Model for content within messages

These models define the schema for the Responses API and provide validation for incoming requests.

**When to add to this file**: Add new models or extend existing ones when:
- Adding support for new request parameters
- Enhancing validation logic for existing parameters
- Adding new data structures for request/response handling

## Usage in the Application

The models are used throughout the application:

1. In `server.py` for request validation and type hinting
2. In handler functions to process typed request data
3. In utility functions that work with request/response data

## Example Model

```python
class ResponseRequest(BaseModel):
    model: str
    input: str
    temperature: float = 1.0
    stream: bool = False
    # ... other fields

    class Config:
        # Pydantic configuration
        schema_extra = {
            "example": {
                "model": "mistral",
                "input": "Write a haiku about AI",
                "temperature": 0.7,
                "stream": False
            }
        }
```

## Integration with FastAPI

FastAPI uses these Pydantic models for:

- Request validation
- Request body parsing
- API documentation generation (via OpenAPI/Swagger)
- Response serialization

## Adding New Models

When adding new models:

1. Define the model class using Pydantic's `BaseModel`
2. Add appropriate type annotations for all fields
3. Add default values for optional fields
4. Add validation using Pydantic field validators if needed
5. Export the model in `__init__.py`