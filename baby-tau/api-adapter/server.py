#!/usr/bin/env python3
"""
API Adapter Server

This server provides a compatibility layer between the OpenAI Responses API
and Chat Completions API formats, allowing applications to use either format.
"""

import os
import uuid
import logging
from typing import List, Dict, Any, Optional, Union
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
import httpx
import uvicorn
from pydantic import BaseModel, Field
import json
import time
from collections import deque
from datetime import datetime
from fastapi.responses import JSONResponse

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("api-adapter")

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

# Define environment variables
OPENAI_BASE_URL_INTERNAL = os.getenv("OPENAI_BASE_URL_INTERNAL", "http://localhost:8000")
OPENAI_BASE_URL = os.getenv("OPENAI_BASE_URL", "http://localhost:8080")
# split OPENAI_BASE_URL into host and port
API_ADAPTER_PORT = int(OPENAI_BASE_URL.split(":")[-1])
API_ADAPTER_HOST = OPENAI_BASE_URL.split(":")[1].replace("//", "")

logger.info(f"Extracted API Adapter Host: {API_ADAPTER_HOST}, Port: {API_ADAPTER_PORT}")

OPENAI_BASE_URL_STRIPPED = OPENAI_BASE_URL_INTERNAL

logger.info(f"Using LLM API base URL: {OPENAI_BASE_URL_STRIPPED}")

# In-memory log storage for recent requests and responses
MAX_LOG_ENTRIES = 50
request_logs = deque(maxlen=MAX_LOG_ENTRIES)

def log_request_response(request_id, details):
    """Add a request/response pair to the logs with timestamp"""
    entry = {
        "timestamp": datetime.now().isoformat(),
        "request_id": request_id,
        **details
    }
    request_logs.appendleft(entry)
    return entry

# Chat Completions models
class ChatCompletionMessage(BaseModel):
    role: str
    content: str
    name: Optional[str] = None

class ChatCompletionRequest(BaseModel):
    model: str
    messages: List[ChatCompletionMessage]
    temperature: Optional[float] = None
    top_p: Optional[float] = None
    n: Optional[int] = 1
    stream: Optional[bool] = False
    max_tokens: Optional[int] = None
    presence_penalty: Optional[float] = None
    frequency_penalty: Optional[float] = None
    stop: Optional[Union[str, List[str]]] = None
    user: Optional[str] = None

# Responses API models
class ResponseContent(BaseModel):
    type: str = "output_text"
    text: str
    annotations: List[Any] = Field(default_factory=list)

class ResponseMessage(BaseModel):
    id: str = Field(default_factory=lambda: f"msg_{uuid.uuid4().hex}")
    type: str = "message"
    role: str
    content: List[ResponseContent]

class ResponseRequest(BaseModel):
    model: str
    input: Union[List[Dict[str, Any]], str]
    temperature: Optional[float] = None
    top_p: Optional[float] = None
    max_tokens: Optional[int] = None
    stream: Optional[bool] = False
    previous_response_id: Optional[str] = None
    store: Optional[bool] = True

@app.post("/v1/chat/completions")
async def chat_completions(request: ChatCompletionRequest):
    """
    Handle Chat Completions API requests by converting to Responses format
    and forwarding to the actual LLM API.
    """
    request_id = uuid.uuid4().hex[:8]
    logger.info(f"[{request_id}] Received Chat Completions request for model: {request.model}")
    logger.info(f"[{request_id}] Request data: {request.dict()}")
    
    # Convert Chat Completions format to Responses format
    responses_request = {
        "model": request.model,
        "input": request.messages,
        "temperature": request.temperature,
        "top_p": request.top_p,
        "max_tokens": request.max_tokens,
        "stream": request.stream,
    }
    
    # Filter out None values
    responses_request = {k: v for k, v in responses_request.items() if v is not None}
    
    try:
        # Forward to the actual API
        async with httpx.AsyncClient() as client:
            logger.info(f"[{request_id}] Forwarding to {OPENAI_BASE_URL}/responses: {responses_request}")
            start_time = time.time()
            response = await client.post(
                f"{OPENAI_BASE_URL}/responses",
                json=responses_request,
                timeout=120.0
            )
            end_time = time.time()
            logger.info(f"[{request_id}] Request completed in {end_time - start_time:.2f}s with status {response.status_code}")
            
            response_data = response.json()
            logger.info(f"[{request_id}] Raw response data: {response_data}")
            
            # Convert Responses format back to Chat Completions format
            if request.stream:
                # Streaming response handling would go here
                # This is more complex and would need to convert streaming events
                return response_data
            else:
                # Simple conversion for non-streaming
                output_text = response_data.get("output_text", "")
                if not output_text and "content" in response_data:
                    for content_item in response_data.get("content", []):
                        if content_item.get("type") == "output_text":
                            output_text = content_item.get("text", "")
                            break
                
                return_data = {
                    "id": f"chatcmpl-{uuid.uuid4().hex}",
                    "object": "chat.completion",
                    "created": response_data.get("created", int(uuid.uuid1().time // 10**6)),
                    "model": request.model,
                    "choices": [
                        {
                            "index": 0,
                            "message": {
                                "role": "assistant",
                                "content": output_text,
                            },
                            "finish_reason": "stop"
                        }
                    ],
                    "usage": response_data.get("usage", {
                        "prompt_tokens": 0,
                        "completion_tokens": 0,
                        "total_tokens": 0
                    })
                }
                
                # Log full request/response cycle for debugging
                log_entry = log_request_response(request_id, {
                    "type": "chat_completions_api",
                    "original_request": request.dict(),
                    "converted_request": responses_request,
                    "llm_response": response_data,
                    "final_response": return_data
                })
                
                logger.info(f"[{request_id}] Returning Chat Completions response: {str(return_data)[:500]}...")
                return return_data
                
    except Exception as e:
        logger.error(f"[{request_id}] Error forwarding request: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error forwarding request: {str(e)}")

# Add a duplicate route for /chat/completions (without the v1 prefix)
@app.post("/chat/completions")
async def chat_completions_without_prefix(request: ChatCompletionRequest):
    """
    Handle Chat Completions API requests without the /v1/ prefix
    """
    logger.info(f"Received Chat Completions request (without v1 prefix) for model: {request.model}")
    return await chat_completions(request)

@app.post("/v1/responses")
async def responses(request: ResponseRequest):
    """
    Handle Responses API requests by converting to Chat Completions format
    and forwarding to the actual LLM API.
    """
    request_id = uuid.uuid4().hex[:8]
    logger.info(f"[{request_id}] Received Responses request for model: {request.model}")
    
    # Log input in detailed format for debugging
    if isinstance(request.input, str):
        logger.info(f"[{request_id}] Raw input (string): {request.input}")
    else:
        logger.info(f"[{request_id}] Raw input (list): {json.dumps(request.input, default=str)}")
    
    # Convert input format if it's a string
    if isinstance(request.input, str):
        messages = [{"role": "user", "content": request.input}]
    else:
        # Process the input messages more carefully to ensure valid format
        messages = []
        for msg in request.input:
            logger.info(f"Processing message: {msg}")
            if isinstance(msg, dict):
                # Make sure message has both role and content
                if "role" in msg:
                    # Handle different content formats
                    content = ""
                    if "content" in msg:
                        # If content is a list (OpenAI Responses format)
                        if isinstance(msg["content"], list):
                            logger.info(f"Content is a list: {msg['content']}")
                            # Extract text from the list of content items
                            text_parts = []
                            for content_item in msg["content"]:
                                if isinstance(content_item, dict):
                                    # Handle known content types
                                    if content_item.get("type") == "input_text" or content_item.get("type") == "output_text":
                                        if "text" in content_item:
                                            text_parts.append(content_item["text"])
                                    elif "text" in content_item:
                                        text_parts.append(content_item["text"])
                            # Join all text parts
                            content = " ".join(text_parts)
                            logger.info(f"Extracted content: '{content}'")
                        # If content is a string
                        elif isinstance(msg["content"], str):
                            content = msg["content"]
                        # If content is something else
                        else:
                            logger.warning(f"Unexpected content type: {type(msg['content'])}, trying to convert to string")
                            try:
                                content = str(msg["content"])
                            except:
                                content = ""
                    
                    # Create properly formatted message
                    message = {
                        "role": msg["role"],
                        "content": content
                    }
                    
                    # Add name if it exists
                    if "name" in msg and msg["name"]:
                        message["name"] = msg["name"]
                        
                    messages.append(message)
    
    # Debug log to see what's being sent
    logger.info(f"[{request_id}] Converted messages format: {json.dumps(messages, default=str)}")
    
    # Convert Responses format to Chat Completions format
    chat_request = {
        "model": request.model,
        "messages": messages,
        "temperature": request.temperature,
        "top_p": request.top_p,
        "max_tokens": request.max_tokens,
        "stream": request.stream,
    }
    
    # Filter out None values
    chat_request = {k: v for k, v in chat_request.items() if v is not None}
    
    logger.info(f"[{request_id}] Final chat request: {json.dumps(chat_request, default=str)}")
    
    try:
        # Forward to the chat completions API endpoint
        async with httpx.AsyncClient() as client:
            logger.info(f"[{request_id}] Sending request to {OPENAI_BASE_URL_STRIPPED}/v1/chat/completions")
            start_time = time.time()
            response = await client.post(
                f"{OPENAI_BASE_URL_STRIPPED}/v1/chat/completions",
                json=chat_request,
                timeout=120.0
            )
            end_time = time.time()
            logger.info(f"[{request_id}] API request completed in {end_time - start_time:.2f}s with status {response.status_code}")
            
            # Check for errors
            if response.status_code != 200:
                logger.error(f"API returned status {response.status_code}: {response.text}")
                # Additional debugging for error cases
                logger.error(f"Request that caused error: {chat_request}")
                raise HTTPException(status_code=response.status_code, detail=response.text)
                
            # Log raw response for debugging
            logger.info(f"[{request_id}] Raw response from API: {response.text}")
            
            # Convert Chat Completions format back to Responses format
            if request.stream:
                # For streaming requests, we need to directly stream the response
                # back to the client rather than trying to parse it
                from fastapi.responses import StreamingResponse
                
                async def stream_generator():
                    # Simply pass through the streaming content directly
                    yield response.content
                
                logger.info(f"[{request_id}] Streaming response back to client")
                return StreamingResponse(
                    content=stream_generator(),
                    media_type="text/event-stream",
                    headers={
                        "Cache-Control": "no-cache",
                        "Connection": "keep-alive",
                        "Content-Type": "text/event-stream",
                    }
                )
            else:
                # For non-streaming requests, parse the JSON
                chat_data = response.json()
                logger.info(f"[{request_id}] Parsed response JSON: {json.dumps(chat_data, default=str)}")
                
                # Get the content from the first choice
                content = ""
                if chat_data.get("choices") and len(chat_data["choices"]) > 0:
                    content = chat_data["choices"][0].get("message", {}).get("content", "")
                
                # Create a response in Responses format
                response_id = f"resp_{uuid.uuid4().hex}"
                created_at = chat_data.get("created", int(uuid.uuid1().time // 10**6))
                
                # Format according to OpenAI Responses API format
                response_data = {
                    "id": response_id,
                    "object": "thread.message",
                    "created_at": created_at,
                    "thread_id": f"thread_{uuid.uuid4().hex}",
                    "model": request.model,
                    "role": "assistant",
                    "content": [
                        {
                            "type": "output_text",
                            "text": content,
                            "annotations": []
                        }
                    ],
                    "output_text": content,
                    "metadata": {},
                    "usage": chat_data.get("usage", {
                        "prompt_tokens": 0,
                        "completion_tokens": 0,
                        "total_tokens": 0
                    })
                }
                
                # Log full request/response cycle for debugging
                log_entry = log_request_response(request_id, {
                    "type": "responses_api",
                    "original_request": request.dict(),
                    "converted_request": chat_request,
                    "llm_response": chat_data,
                    "final_response": response_data
                })
                
                logger.info(f"[{request_id}] Formatted response data: {json.dumps(response_data, default=str)}")
                logger.info(f"[{request_id}] Request handling complete, returning response")
                return response_data
                
    except httpx.HTTPError as e:
        logger.error(f"[{request_id}] HTTP error forwarding request: {str(e)}")
        raise HTTPException(status_code=502, detail=f"Error communicating with API: {str(e)}")
    except Exception as e:
        logger.error(f"[{request_id}] Error forwarding request: {str(e)}")
        logger.exception(f"[{request_id}] Full exception details:")
        raise HTTPException(status_code=500, detail=f"Error forwarding request: {str(e)}")

# Add a duplicate route for /responses (without the v1 prefix)
@app.post("/responses")
async def responses_without_prefix(request: ResponseRequest):
    """
    Handle Responses API requests without the /v1/ prefix
    """
    request_id = uuid.uuid4().hex[:8]
    logger.info(f"[{request_id}] Received Responses request (without v1 prefix) for model: {request.model}")
    return await responses(request)

# Proxy all other requests unchanged
@app.api_route("/{path:path}", methods=["GET", "POST", "PUT", "DELETE", "OPTIONS", "HEAD", "PATCH"])
async def proxy(request: Request, path: str):
    """
    Proxy all other requests to the actual API unchanged.
    """
    request_id = uuid.uuid4().hex[:8]
    logger.info(f"[{request_id}] Proxying request to path: {path}")
    
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
        
        # Log request body for debugging if not too large
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
        
        async with httpx.AsyncClient() as client:
            # Forward the request
            start_time = time.time()
            response = await client.request(
                method=method,
                url=target_url,
                params=params,
                headers=headers,
                content=body,
                timeout=120.0
            )
            end_time = time.time()
            logger.info(f"[{request_id}] Proxy request completed in {end_time - start_time:.2f}s with status {response.status_code}")
            
            # Check for errors
            if response.status_code >= 400:
                logger.warning(f"[{request_id}] API returned error status {response.status_code}: {response.text}")
                return response.json() if response.headers.get("content-type") == "application/json" else response.text
            
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

# Add a debugging endpoint to view recent logs
@app.get("/debug/logs")
async def get_logs(limit: int = 10, request_id: str = None):
    """
    Endpoint to view recent request/response logs for debugging
    """
    if limit > MAX_LOG_ENTRIES:
        limit = MAX_LOG_ENTRIES
        
    if request_id:
        # Filter logs by request_id
        filtered_logs = [log for log in request_logs if log["request_id"] == request_id]
        return JSONResponse(content={"logs": filtered_logs})
    else:
        # Return most recent logs up to limit
        return JSONResponse(content={"logs": list(request_logs)[:limit]})

@app.get("/debug/request/{request_id}")
async def get_request_detail(request_id: str):
    """
    Get detailed information about a specific request by ID
    """
    for log in request_logs:
        if log["request_id"] == request_id:
            return JSONResponse(content=log)
    
    raise HTTPException(status_code=404, detail="Request ID not found in logs")

if __name__ == "__main__":
    logger.info(f"Starting API adapter server on {API_ADAPTER_HOST}:{API_ADAPTER_PORT}")
    uvicorn.run(app, host=API_ADAPTER_HOST, port=API_ADAPTER_PORT)
