"""
Handler for proxying requests to the backend API.
"""

import time
import httpx
from fastapi import Request, HTTPException
from typing import Dict, Any

from utils import generate_request_id, log_request_details
from config import OPENAI_BASE_URL_STRIPPED, REQUEST_TIMEOUT, logger

async def handle_proxy(request: Request, path: str):
    """
    Proxy all other requests to the actual API unchanged.
    """
    request_id = generate_request_id()
    await log_request_details(request_id, request, path)
    
    try:
        # Get request details
        method = request.method
        headers = dict(request.headers)
        params = dict(request.query_params)
        
        # Fix path to always have v1 prefix when sending to backend
        if not path.startswith('v1/') and not path.startswith('/v1/'):
            target_url = f"{OPENAI_BASE_URL_STRIPPED}/v1/{path}"
        else:
            # If path already has v1, don't add another one
            cleaned_path = path.replace('v1/v1', 'v1').lstrip('v1/')
            target_url = f"{OPENAI_BASE_URL_STRIPPED}/v1/{cleaned_path}"
            
        logger.info(f"[{request_id}] Proxying to: {target_url} (method: {method})")
        
        # Remove headers that might cause issues
        headers.pop("host", None)
        
        # Get the request body
        body = await request.body()
        
        async with httpx.AsyncClient() as client:
            # Forward the request
            start_time = time.time()
            try:
                response = await client.request(
                    method=method,
                    url=target_url,
                    params=params,
                    headers=headers,
                    content=body,
                    timeout=REQUEST_TIMEOUT
                )
                end_time = time.time()
                logger.info(f"[{request_id}] Proxy request completed in {end_time - start_time:.2f}s with status {response.status_code}")
            except httpx.TimeoutException as e:
                logger.error(f"[{request_id}] Proxy request timed out after {time.time() - start_time:.2f}s: {str(e)}")
                raise HTTPException(status_code=504, detail=f"Request timed out: {str(e)}")
            except httpx.ConnectError as e:
                logger.error(f"[{request_id}] Proxy connection error: {str(e)}")
                raise HTTPException(status_code=503, detail=f"Connection error: {str(e)}")
            
            # Check for errors
            if response.status_code >= 400:
                logger.warning(f"[{request_id}] API returned error status {response.status_code}: {response.text}")
            
            # Log response for debugging if not too large
            if len(response.content) < 10000:
                logger.info(f"[{request_id}] Response content: {response.text}")
            else:
                logger.info(f"[{request_id}] Response content: (large data, {len(response.content)} bytes)")
            
            # Return the response
            try:
                return response.json()
            except ValueError:
                # If it's not JSON, return the raw content
                return response.text
    except httpx.HTTPError as e:
        logger.error(f"[{request_id}] HTTP error proxying request to path '{path}': {str(e)}")
        raise HTTPException(status_code=502, detail=f"Error communicating with API: {str(e)}")
    except Exception as e:
        logger.error(f"[{request_id}] Error proxying request to path '{path}': {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error proxying request: {str(e)}")
