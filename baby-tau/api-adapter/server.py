#!/usr/bin/env python3
"""
API Adapter Server

This server provides a compatibility layer between the OpenAI Responses API
and Chat Completions API formats, allowing applications to use either format.
"""

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
import uvicorn
import sys
import os

# Add the current directory to sys.path to enable imports
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

# Use absolute imports
from config import API_ADAPTER_HOST, API_ADAPTER_PORT, logger
from models.requests import ResponseRequest
from handlers import handle_responses, handle_proxy, get_logs, get_request_detail

# Create FastAPI app
app = FastAPI(title="API Adapter", description="Adapter between Responses API and Chat Completions API")

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Define routes for Responses API
@app.post("/v1/responses")
async def responses(request: ResponseRequest, raw_request: Request):
    """Handle Responses API requests"""
    return await handle_responses(request, raw_request)

# Add a duplicate route for /responses (without the v1 prefix)
@app.post("/responses")
async def responses_without_prefix(request: ResponseRequest, raw_request: Request):
    """Handle Responses API requests without the /v1/ prefix"""
    return await handle_responses(request, raw_request)

# Debug endpoints
@app.get("/debug/logs")
async def debug_logs(limit: int = 10, request_id: str = None):
    """Endpoint to view recent request/response logs for debugging"""
    return await get_logs(limit, request_id)

@app.get("/debug/request/{request_id}")
async def debug_request_detail(request_id: str):
    """Get detailed information about a specific request by ID"""
    return await get_request_detail(request_id)

# Proxy all other requests unchanged
@app.api_route("/{path:path}", methods=["GET", "POST", "PUT", "DELETE", "OPTIONS", "HEAD", "PATCH"])
async def proxy(request: Request, path: str):
    """Proxy all other requests to the actual API unchanged."""
    return await handle_proxy(request, path)

if __name__ == "__main__":
    logger.info(f"Starting API adapter server on {API_ADAPTER_HOST}:{API_ADAPTER_PORT}")
    uvicorn.run(app, host=API_ADAPTER_HOST, port=API_ADAPTER_PORT)
