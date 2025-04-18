#!/usr/bin/env python3
"""
Configuration settings for API adapter.
"""

import os
import logging

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("api-adapter")

# API URLs and endpoints
OPENAI_BASE_URL_INTERNAL = os.getenv("OPENAI_BASE_URL_INTERNAL", "http://localhost:8000")
OPENAI_BASE_URL = os.getenv("OPENAI_BASE_URL", "http://localhost:8080")

# Parse host and port from base URL
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

# Stripped base URL for forwarding requests
OPENAI_BASE_URL_STRIPPED = OPENAI_BASE_URL_INTERNAL
logger.info(f"Using LLM API base URL: {OPENAI_BASE_URL_STRIPPED}")

# Request handling settings
REQUEST_TIMEOUT = 300.0  # seconds
MAX_LOG_ENTRIES = 50
