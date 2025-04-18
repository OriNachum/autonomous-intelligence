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
    max_output_tokens: Optional[int] = None
    status: Optional[str] = None
    error: Optional[str] = None
    incomplete_details: Optional[str] = None
    stream: Optional[bool] = False
    previous_response_id: Optional[str] = None
    store: Optional[bool] = True
    instructions: Optional[str] = None
    reasoning: Optional[Dict[str, Any]] = None
    parallel_tool_calls: Optional[bool] = True
    tool_choice: Optional[str] = None
    tools: Optional[List[Dict[str, Any]]] = None
    truncation: Optional[str] = None
    user: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None

    

@app.post("/v1/responses")
async def responses(request: ResponseRequest, raw_request: Request):
    """
    Handle Responses API requests by converting to Chat Completions format
    and forwarding to the actual LLM API.
    """
    request_id = uuid.uuid4().hex[:8]
    # Add detailed request logging for debugging
    logger.info(f"[{request_id}] ===== INCOMING REQUEST /v1/responses =====")
    logger.info(f"[{request_id}] Headers: {dict(raw_request.headers)}")
    logger.info(f"[{request_id}] Query params: {dict(raw_request.query_params)}")
    logger.info(f"[{request_id}] Received Responses request for model: {request.model}")
    logger.info(f"[{request_id}] Received Responses request: {request}")
    
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
        "max_completion_tokens": request.max_output_tokens,
        "stream": request.stream,
        "store": request.store,
        #"instructions": request.instructions,
        #"parallel_tool_calls": request.parallel_tool_calls,
        #"truncation": request.truncation,
        "user": request.user,
        "metadata": request.metadata,
        #"previous_response_id": request.previous_response_id,
        #"reasoning_effort": request.reasoning.effort,
        
    }
    # add tools if present
    if request.tools:
        chat_request["tools"] = request.tools
        parallel_tool_calls = request.parallel_tool_calls
    if request.tool_choice:
        chat_request["tool_choice"] = request.tool_choice        
    # Add instructions as first message if present (system role)
    if request.instructions:
        chat_request["messages"].insert(0, {
            "role": "system",
            "content": request.instructions
        })
    if request.reasoning and request.reasoning.get("effort"):
        chat_request["reasoning_effort"] = request.reasoning.get("effort")
    # Filter out None values
    chat_request = {k: v for k, v in chat_request.items() if v is not None}
    
    logger.info(f"[{request_id}] Final chat request: {json.dumps(chat_request, default=str)}")
    
    try:
        # Forward to the chat completions API endpoint
        async with httpx.AsyncClient() as client:
            logger.info(f"[{request_id}] Sending request to {OPENAI_BASE_URL_STRIPPED}/v1/chat/completions")
            start_time = time.time()
            try:
                response = await client.post(
                    f"{OPENAI_BASE_URL_STRIPPED}/v1/chat/completions",
                    json=chat_request,
                    timeout=300.0  # Increased from 120.0 to 300.0 seconds (5 minutes)
                )
                end_time = time.time()
                logger.info(f"[{request_id}] API request completed in {end_time - start_time:.2f}s with status {response.status_code}")
                
                # Check for errors
                if response.status_code != 200:
                    logger.error(f"API returned status {response.status_code}: {response.text}")
                    # Additional debugging for error cases
                    logger.error(f"Request that caused error: {chat_request}")
                    raise HTTPException(status_code=response.status_code, detail=response.text)
            except httpx.TimeoutException as e:
                logger.error(f"[{request_id}] Request timed out after {time.time() - start_time:.2f}s: {str(e)}")
                raise HTTPException(status_code=504, detail=f"Request timed out: {str(e)}")
            except httpx.ConnectError as e:
                logger.error(f"[{request_id}] Connection error: {str(e)}")
                raise HTTPException(status_code=503, detail=f"Connection error: {str(e)}")
            except httpx.HTTPError as e:
                logger.error(f"[{request_id}] HTTP error: {str(e)}")
                raise HTTPException(status_code=502, detail=f"HTTP error: {str(e)}")
            
            # Log raw response for debugging
            logger.info(f"[{request_id}] Raw response from API: {response.text}")
            
            # Convert Chat Completions format back to Responses format
            if request.stream:
                # For streaming requests, we need to directly stream the response
                # back to the client rather than trying to parse it
                from fastapi.responses import StreamingResponse
                
                async def stream_generator():
                    # Create a unique response ID for this streaming session
                    response_id = f"resp_{uuid.uuid4().hex}"
                    message_id = f"msg_{uuid.uuid4().hex}"
                    thread_id = f"thread_{uuid.uuid4().hex}"
                    created_at = int(time.time())
                    
                    # Initialize buffer for accumulating content from chunks
                    content_buffer = ""
                    
                    # Track function call arguments by tool call ID
                    function_calls = {}
                    
                    # First send a response.created event
                    response_created = {
                        "type": "response.created",
                        "response": {
                            "id": response_id,
                            "object": "response",
                            "created_at": created_at,
                            "status": "in_progress",
                            "error": None,
                            "incomplete_details": None,
                            "instructions": None,
                            "max_output_tokens": None,
                            "model": request.model,
                            "output": [],
                            "parallel_tool_calls": True,
                            "previous_response_id": None,
                            "reasoning": {
                                "effort": None,
                                "summary": None
                            },
                            "store": request.store,
                            "temperature": request.temperature,
                            "text": {
                                "format": {
                                    "type": "text"
                                }
                            },
                            "tool_choice": "auto",
                            "tools": [],
                            "top_p": request.top_p,
                            "truncation": "disabled",
                            "usage": None,
                            "user": None,
                            "metadata": {}
                        }
                    }
                    
                    yield f"data: {json.dumps(response_created)}\n\n"
                    
                    # Then send an in_progress event 
                    response_in_progress = {
                        "type": "response.in_progress",
                        "response": {
                            "id": response_id,
                            "object": "response",
                            "created_at": created_at,
                            "status": "in_progress",
                            "error": None,
                            "incomplete_details": None,
                            "instructions": None,
                            "max_output_tokens": None,
                            "model": request.model,
                            "output": [],
                            "parallel_tool_calls": True,
                            "previous_response_id": None,
                            "reasoning": {
                                "effort": None,
                                "summary": None
                            },
                            "store": request.store,
                            "temperature": request.temperature,
                            "text": {
                                "format": {
                                    "type": "text"
                                }
                            },
                            "tool_choice": "auto",
                            "tools": [],
                            "top_p": request.top_p,
                            "truncation": "disabled",
                            "usage": None,
                            "user": None,
                            "metadata": {}
                        }
                    }
                    
                    yield f"data: {json.dumps(response_in_progress)}\n\n"
                    
                    # Keep the original lines for debugging
                    async for line in response.aiter_lines():
                        # Keep the original debug logging
                        logger.info(f"[{request_id}] Streaming chunk: {line}")
                        
                        if line.startswith("data: "):
                            try:
                                # Parse the SSE data line
                                data = line[6:]  # Remove "data: " prefix
                                if data.strip() == "[DONE]":
                                    # End of stream marker - send completed response
                                    
                                    # Send any pending function call "done" events
                                    for tool_id, info in function_calls.items():
                                        if not info.get("done_sent", False):
                                            done_event = {
                                                "type": "response.function_call_arguments.done",
                                                "item_id": tool_id,
                                                "output_index": info.get("index", 0),
                                                "arguments": info.get("arguments", ""),
                                                "response_id": response_id
                                            }
                                            yield f"data: {json.dumps(done_event)}\n\n"
                                    
                                    # Prepare output items including both text content and tool calls
                                    output_items = []
                                    
                                    # Include text message if there's any content
                                    if content_buffer.strip():
                                        output_items.append({
                                            "id": message_id,
                                            "type": "message",
                                            "role": "assistant",
                                            "content": [
                                                {
                                                    "type": "output_text",
                                                    "text": content_buffer,
                                                    "annotations": []
                                                }
                                            ]
                                        })
                                    
                                    # Add tool calls to output
                                    for tool_id, info in function_calls.items():
                                        tool_item_id = f"item_{uuid.uuid4().hex}"
                                        output_items.append({
                                            "id": tool_item_id,
                                            "type": "function_call",
                                            "function_call": {
                                                "name": info.get("name", ""),
                                                "arguments": info.get("arguments", ""),
                                                "output": None  # Will be filled by the client when function executes
                                            }
                                        })
                                    
                                    response_completed = {
                                        "type": "response.completed",
                                        "response": {
                                            "id": response_id,
                                            "object": "response",
                                            "created_at": created_at,
                                            "status": "completed",
                                            "error": None,
                                            "incomplete_details": None,
                                            "input": [],
                                            "instructions": None,
                                            "max_output_tokens": None,
                                            "model": request.model,
                                            "output": output_items,
                                            "previous_response_id": None,
                                            "reasoning_effort": None,
                                            "store": request.store,
                                            "temperature": request.temperature,
                                            "text": {
                                                "format": {
                                                    "type": "text"
                                                }
                                            },
                                            "tool_choice": "auto",
                                            "tools": [],
                                            "top_p": request.top_p,
                                            "truncation": "disabled",
                                            "usage": {
                                                "input_tokens": 0,
                                                "output_tokens": 0,
                                                "output_tokens_details": {
                                                    "reasoning_tokens": 0
                                                },
                                                "total_tokens": 0
                                            },
                                            "user": None,
                                            "metadata": {}
                                        }
                                    }
                                    yield f"data: {json.dumps(response_completed)}\n\n"
                                    yield "data: [DONE]\n\n"
                                    continue
                                    
                                # Parse the JSON data from the chunk
                                chunk = json.loads(data)
                                
                                # Extract content from the delta
                                if "choices" in chunk and len(chunk["choices"]) > 0:
                                    choice = chunk["choices"][0]
                                    
                                    # Handle function/tool calls
                                    if "delta" in choice and "tool_calls" in choice["delta"]:
                                        tool_calls = choice["delta"]["tool_calls"]
                                        for tool_call in tool_calls:
                                            # Generate a unique ID for the tool call item if not present
                                            tool_index = tool_call.get("index", 0)
                                            tool_id = tool_call.get("id", f"item_{uuid.uuid4().hex}")
                                            
                                            # Initialize tracking for this tool call if needed
                                            if tool_id not in function_calls:
                                                function_calls[tool_id] = {
                                                    "index": tool_index,
                                                    "arguments": "",
                                                    "name": "",
                                                    "done_sent": False
                                                }
                                            
                                            # Update function name if present
                                            if "function" in tool_call and "name" in tool_call["function"]:
                                                function_calls[tool_id]["name"] = tool_call["function"]["name"]
                                            
                                            # Check for function arguments delta
                                            if "function" in tool_call and "arguments" in tool_call["function"]:
                                                args_delta = tool_call["function"]["arguments"]
                                                function_calls[tool_id]["arguments"] += args_delta
                                                
                                                # Emit function call arguments delta event
                                                delta_event = {
                                                    "type": "response.function_call_arguments.delta",
                                                    "item_id": tool_id,
                                                    "output_index": tool_index,
                                                    "delta": args_delta,
                                                    "response_id": response_id
                                                }
                                                yield f"data: {json.dumps(delta_event)}\n\n"
                                                
                                                # If we got complete arguments in one chunk, also emit the done event
                                                # This handles the case where arguments come complete and not as separate deltas
                                                if (choice.get("finish_reason") == "tool_calls" or 
                                                    tool_call.get("function", {}).get("name")):
                                                    if not function_calls[tool_id]["done_sent"]:
                                                        done_event = {
                                                            "type": "response.function_call_arguments.done",
                                                            "item_id": tool_id,
                                                            "output_index": tool_index,
                                                            "arguments": function_calls[tool_id]["arguments"],
                                                            "response_id": response_id
                                                        }
                                                        function_calls[tool_id]["done_sent"] = True
                                                        yield f"data: {json.dumps(done_event)}\n\n"
                                    
                                    # Check if this choice indicates tool calls are finished
                                    # This handles the case where finish_reason comes in a separate chunk
                                    if (choice.get("finish_reason") == "tool_calls" or
                                        choice.get("finish_details", {}).get("type") == "tool_calls"):
                                        logger.info(f"[{request_id}] Detected tool_calls finish_reason, sending done events")
                                        # Mark all tracked tool calls as done and emit done events
                                        for tool_id, info in function_calls.items():
                                            if not info.get("done_sent", False):
                                                done_event = {
                                                    "type": "response.function_call_arguments.done",
                                                    "item_id": tool_id,
                                                    "output_index": info.get("index", 0),
                                                    "arguments": info.get("arguments", ""),
                                                    "response_id": response_id
                                                }
                                                function_calls[tool_id]["done_sent"] = True
                                                yield f"data: {json.dumps(done_event)}\n\n"
                                    
                                    # Handle regular text content
                                    if "delta" in choice and "content" in choice["delta"]:
                                        content = choice["delta"]["content"]
                                        content_buffer += content
                                        
                                        # For intermediate chunks, use delta format
                                        delta_event = {
                                            "type": "message.delta",
                                            "delta": {
                                                "message_id": message_id,
                                                "type": "message",
                                                "content": [
                                                    {
                                                        "type": "output_text",
                                                        "text": content,
                                                        "annotations": []
                                                    }
                                                ]
                                            },
                                            "response_id": response_id
                                        }
                                        
                                        # Format as SSE and yield
                                        yield f"data: {json.dumps(delta_event)}\n\n"
                            except json.JSONDecodeError:
                                logger.warning(f"[{request_id}] Could not parse streaming JSON: {line}")
                                # Just pass through the line as-is if we can't parse it
                                yield f"{line}\n\n"
                            except Exception as e:
                                logger.error(f"[{request_id}] Error processing stream chunk: {str(e)}")
                                yield f"data: {json.dumps({'error': str(e)})}\n\n"
                        elif line.strip():
                            # Pass through any non-empty lines that don't start with "data: "
                            yield f"{line}\n\n"
                
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
async def responses_without_prefix(request: ResponseRequest, raw_request: Request):
    """
    Handle Responses API requests without the /v1/ prefix
    """
    request_id = uuid.uuid4().hex[:8]
    logger.info(f"[{request_id}] ===== INCOMING REQUEST /responses =====")
    logger.info(f"[{request_id}] Headers: {dict(raw_request.headers)}")
    logger.info(f"[{request_id}] Query params: {dict(raw_request.query_params)}")
    logger.info(f"[{request_id}] Received Responses request (without v1 prefix) for model: {request.model}")
    return await responses(request, raw_request)

# Proxy all other requests unchanged
@app.api_route("/{path:path}", methods=["GET", "POST", "PUT", "DELETE", "OPTIONS", "HEAD", "PATCH"])
async def proxy(request: Request, path: str):
    """
    Proxy all other requests to the actual API unchanged.
    """
    request_id = uuid.uuid4().hex[:8]
    # Add detailed request logging for debugging
    logger.info(f"[{request_id}] ===== INCOMING REQUEST /{path} =====")
    logger.info(f"[{request_id}] Headers: {dict(request.headers)}")
    logger.info(f"[{request_id}] Query params: {dict(request.query_params)}")
    logger.info(f"[{request_id}] Method: {request.method}")
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
            try:
                response = await client.request(
                    method=method,
                    url=target_url,
                    params=params,
                    headers=headers,
                    content=body,
                    timeout=300.0  # Increased from 120.0 to 300.0 seconds (5 minutes)
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
