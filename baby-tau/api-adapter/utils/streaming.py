"""
Utilities for handling streaming responses.
This module re-exports the stream_generator function from stream_processor.py
to maintain API compatibility while avoiding code duplication.
"""

# Re-export the stream_generator function from the main implementation
import uuid

# This avoids code duplication by having a single implementation of stream_generator
# while maintaining backwards compatibility with code that imports from utils.streaming

import json
import time
from typing import Dict, Any, AsyncGenerator
import httpx
from config import logger
