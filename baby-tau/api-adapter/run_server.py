#!/usr/bin/env python3
"""
Entry point script to run the API adapter server.
"""

import uvicorn
from .config import API_ADAPTER_HOST, API_ADAPTER_PORT, logger

if __name__ == "__main__":
    logger.info(f"Starting API adapter server on {API_ADAPTER_HOST}:{API_ADAPTER_PORT}")
    uvicorn.run("api-adapter.server:app", host=API_ADAPTER_HOST, port=API_ADAPTER_PORT, reload=True)
