# config.py Documentation

## Overview

`config.py` contains all configuration settings for the API adapter. It manages environment variables, logging setup, and other global settings used throughout the application.

## Key Components

### Environment Variables

The file reads configuration from environment variables:

```python
# API URLs and endpoints
OPENAI_BASE_URL_INTERNAL = os.getenv("OPENAI_BASE_URL_INTERNAL", "http://localhost:8000")
OPENAI_BASE_URL = os.getenv("OPENAI_BASE_URL", "http://localhost:8080")
```

- `OPENAI_BASE_URL_INTERNAL`: The URL of the backend LLM API
- `OPENAI_BASE_URL`: The URL where this adapter is accessible

### Logging Configuration

```python
# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("api-adapter")
```

Sets up the logger used throughout the application for tracking events and errors.

### Host and Port Parsing

```python
def parse_host_port():
    try:
        API_ADAPTER_PORT = int(OPENAI_BASE_URL.split(":")[-1])
        API_ADAPTER_HOST = OPENAI_BASE_URL.split(":")[1].replace("//", "")
        logger.info(f"Extracted API Adapter Host: {API_ADAPTER_HOST}, Port: {API_ADAPTER_PORT}")
        return API_ADAPTER_HOST, API_ADAPTER_PORT
    except Exception as e:
        logger.error(f"Error parsing host/port from URL: {e}")
        return "localhost", 8080

API_ADAPTER_HOST, API_ADAPTER_PORT = parse_host_port()
```

This function extracts the host and port from the `OPENAI_BASE_URL` environment variable for the server to listen on.

### Request Settings

```python
# Request handling settings
REQUEST_TIMEOUT = 300.0  # seconds
MAX_LOG_ENTRIES = 50
```

- `REQUEST_TIMEOUT`: Maximum time (in seconds) to wait for a response from the LLM API
- `MAX_LOG_ENTRIES`: Maximum number of log entries to keep in memory

## Usage in the Application

The configuration is imported and used throughout the application:

- `server.py` uses the host and port settings
- Handler functions use the base URL and timeout settings
- Logging functions use the logger instance

## When to Modify

Modify this file when:

1. Adding new configuration parameters
2. Changing default values
3. Adding support for new environment variables
4. Enhancing logging configuration
5. Adding new helper functions related to configuration

## Best Practices

When working with `config.py`:

1. Always provide sensible defaults for environment variables
2. Log configuration values on startup
3. Use clear, descriptive variable names
4. Group related configuration settings together
5. Document the purpose and expected values of each setting