"""
Logging utilities for the API adapter.
"""

import logging
import json
import uuid
from datetime import datetime
from collections import deque
from typing import Dict, Any, Deque
from fastapi import Request

# Change relative import to absolute import
from config import MAX_LOG_ENTRIES, logger

# In-memory log storage for recent requests and responses
request_logs: Deque[Dict[str, Any]] = deque(maxlen=MAX_LOG_ENTRIES)

def log_request_response(request_id: str, details: Dict[str, Any]) -> Dict[str, Any]:
    """Add a request/response pair to the logs with timestamp"""
    entry = {
        "timestamp": datetime.now().isoformat(),
        "request_id": request_id,
        **details
    }
    request_logs.appendleft(entry)
    return entry

def generate_request_id() -> str:
    """Generate a short request ID for tracking"""
    return uuid.uuid4().hex[:8]

async def log_request_details(request_id: str, request: Request, path: str = None):
    """Log detailed request information for debugging"""
    path_info = f"/{path}" if path else ""
    logger.info(f"[{request_id}] ===== INCOMING REQUEST {path_info} =====")
    logger.info(f"[{request_id}] Headers: {dict(request.headers)}")
    logger.info(f"[{request_id}] Query params: {dict(request.query_params)}")
    logger.info(f"[{request_id}] Method: {request.method}")
    
    # Get the request body if available
    try:
        body = await request.body()
        if len(body) < 10000:  # Only log if body is smaller than 10KB
            try:
                body_str = body.decode('utf-8')
                try:
                    body_json = json.loads(body_str)
                    logger.info(f"[{request_id}] Request body (JSON): {json.dumps(body_json, default=str)}")
                except:
                    logger.info(f"[{request_id}] Request body (text): {body_str}")
            except:
                logger.info(f"[{request_id}] Request body: (binary data, {len(body)} bytes)")
        else:
            logger.info(f"[{request_id}] Request body: (large data, {len(body)} bytes)")
        
        # Reset the body position for further processing
        await request.body()
    except:
        # Unable to read body or body already consumed
        pass
