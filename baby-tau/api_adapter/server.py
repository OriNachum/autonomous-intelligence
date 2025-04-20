#!/usr/bin/env python3

import os
import json
import asyncio
import logging
from typing import Dict, List, Any, Optional, Union
import uuid
from fastapi import FastAPI, Request, Response, BackgroundTasks, HTTPException, Depends
from fastapi.responses import StreamingResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
import uvicorn
import httpx
from pydantic import BaseModel, Field
import time
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger("api_adapter")

# Configuration from environment variables
OPENAI_BASE_URL_INTERNAL = os.environ.get("OPENAI_BASE_URL_INTERNAL", "http://localhost:8000")
OPENAI_BASE_URL_INTERNAL = f"{OPENAI_BASE_URL_INTERNAL}/v1"
OPENAI_BASE_URL = os.environ.get("OPENAI_BASE_URL", "http://localhost:8080")
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY", "dummy-key")
API_ADAPTER_HOST = os.environ.get("API_ADAPTER_HOST", "0.0.0.0")
API_ADAPTER_PORT = int(os.environ.get("API_ADAPTER_PORT", "8080"))

app = FastAPI(title="API Adapter", description="Adapter for Responses API to chat.completions API")

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# HTTP client for making requests to the LLM API
http_client = httpx.AsyncClient(
    base_url=f"OPENAI_BASE_URL_INTERNAL",
    headers={"Authorization": f"Bearer {OPENAI_API_KEY}"},
    timeout=httpx.Timeout(60.0)
)

# Pydantic models for requests and responses
class ToolFunction(BaseModel):
    name: str
    description: Optional[str] = None
    parameters: Optional[Dict] = None

class Tool(BaseModel):
    type: str = "function"
    function: ToolFunction

class OutputText(BaseModel):
    type: str = "output_text"
    text: str

class Message(BaseModel):
    id: Optional[str] = None
    type: str = "message"
    role: str
    content: List[Any]

class TextFormat(BaseModel):
    type: str = "text"

class ResponseItem(BaseModel):
    id: str
    type: str
    role: str
    content: List[Any]

class ResponseModel(BaseModel):
    id: str
    object: str = "response"
    created_at: int
    status: str = "in_progress"
    error: Optional[Any] = None
    incomplete_details: Optional[Any] = None
    instructions: Optional[str] = None
    max_output_tokens: Optional[int] = None
    model: str
    output: List[Any] = []
    parallel_tool_calls: bool = True
    previous_response_id: Optional[str] = None
    reasoning: Dict = Field(default_factory=lambda: {"effort": None, "summary": None})
    store: bool = False
    temperature: float = 1.0
    text: Dict = Field(default_factory=lambda: {"format": {"type": "text"}})
    tool_choice: str = "auto"
    tools: List[Tool] = []
    top_p: float = 1.0
    truncation: str = "disabled"
    usage: Optional[Dict] = None
    user: Optional[str] = None
    metadata: Dict = Field(default_factory=dict)

class ResponseCreateRequest(BaseModel):
    model: str
    input: Optional[List[Any]] = None
    tools: Optional[List[Tool]] = None
    tool_choice: Optional[str] = "auto"
    stream: Optional[bool] = False
    temperature: Optional[float] = 1.0
    top_p: Optional[float] = 1.0
    max_output_tokens: Optional[int] = None
    user: Optional[str] = None
    metadata: Optional[Dict] = None

class ToolCallArgumentsDelta(BaseModel):
    type: str = "response.tool_calls.arguments.delta"
    item_id: str
    output_index: int
    delta: str

class ToolCallArgumentsDone(BaseModel):
    type: str = "response.tool_calls.arguments.done"
    item_id: str
    output_index: int
    arguments: str

class ToolCallsCreated(BaseModel):
    type: str = "response.tool_calls.created"
    item_id: str
    output_index: int
    tool_call: Dict

class OutputTextDelta(BaseModel):
    type: str = "response.output_text.delta"
    item_id: str
    output_index: int
    delta: str

class ResponseCreated(BaseModel):
    type: str = "response.created"
    response: ResponseModel

class ResponseInProgress(BaseModel):
    type: str = "response.in_progress"
    response: ResponseModel

class ResponseCompleted(BaseModel):
    type: str = "response.completed"
    response: ResponseModel

# Helper functions
def current_timestamp() -> int:
    return int(time.time())

def convert_responses_to_chat_completions(request_data: dict) -> dict:
    """
    Convert a request in Responses API format to chat.completions API format.
    """
    chat_request = {
        "model": request_data.get("model"),
        "temperature": request_data.get("temperature", 1.0),
        "top_p": request_data.get("top_p", 1.0),
        "stream": request_data.get("stream", False),
    }

    # Convert any max_output_tokens to max_tokens
    if "max_output_tokens" in request_data:
        chat_request["max_tokens"] = request_data["max_output_tokens"]

    # Convert input to messages
    messages = []
    
    # Check for previous tool responses in the input
    if "input" in request_data and request_data["input"]:
        user_message = {"role": "user", "content": ""}
        
        for item in request_data["input"]:
            if isinstance(item, dict):
                if item.get("type") == "message" and item.get("role") == "user":
                    # Add user message
                    content = ""
                    if "content" in item:
                        for content_item in item["content"]:
                            if content_item.get("type") == "text":
                                content = content_item.get("text", "")
                    user_message = {"role": "user", "content": content}
                    messages.append(user_message)
                    
                elif item.get("type") == "function_call_output":
                    # Add tool output
                    messages.append({
                        "role": "tool",
                        "tool_call_id": item.get("call_id"),
                        "content": item.get("output", "")
                    })
            elif isinstance(item, str):
                # Simple string input
                messages.append({"role": "user", "content": item})
    
    # If no messages were created, add an empty user message
    if not messages:
        messages.append({"role": "user", "content": ""})
    
    chat_request["messages"] = messages

    # Convert tools
    if "tools" in request_data and request_data["tools"]:
        chat_request["tools"] = []
        for tool in request_data["tools"]:
            if tool.get("type") == "function":
                chat_request["tools"].append({
                    "type": "function",
                    "function": {
                        "name": tool["function"]["name"],
                        "description": tool["function"].get("description", ""),
                        "parameters": tool["function"].get("parameters", {})
                    }
                })
    
    # Handle tool_choice
    if "tool_choice" in request_data:
        chat_request["tool_choice"] = request_data["tool_choice"]
    
    # Add optional parameters if they exist
    for key in ["user", "metadata"]:
        if key in request_data and request_data[key] is not None:
            chat_request[key] = request_data[key]
    
    return chat_request

async def process_chat_completions_stream(response):
    """
    Process the streaming response from chat.completions API.
    Tracks the state of tool calls to properly convert them to Responses API events.
    """
    tool_calls = {}  # Store tool calls being built
    response_id = f"resp_{uuid.uuid4().hex}"
    tool_call_counter = 0
    message_id = f"msg_{uuid.uuid4().hex}"
    
    # Create and yield the initial response.created event
    response_obj = ResponseModel(
        id=response_id,
        created_at=current_timestamp(),
        model="", # Will be filled from the first chunk
        output=[]
    )
    
    created_event = ResponseCreated(
        type="response.created",
        response=response_obj
    )
    
    yield f"data: {json.dumps(created_event.dict())}\n\n"
    
    # Also emit the in_progress event
    in_progress_event = ResponseInProgress(
        type="response.in_progress",
        response=response_obj
    )
    
    yield f"data: {json.dumps(in_progress_event.dict())}\n\n"
    
    try:
        async for chunk in response.aiter_lines():
            if not chunk.strip():
                continue
                
            # Skip prefix if present
            if chunk.startswith("data: "):
                chunk = chunk[6:]
                
            try:
                data = json.loads(chunk)
                
                # Extract model name from the first chunk if available
                if "model" in data and response_obj.model == "":
                    response_obj.model = data["model"]
                
                # Check for delta choices
                if "choices" in data and data["choices"]:
                    choice = data["choices"][0]
                    
                    # Process delta
                    if "delta" in choice:
                        delta = choice["delta"]
                        
                        # Handle tool calls
                        if "tool_calls" in delta and delta["tool_calls"]:
                            for tool_delta in delta["tool_calls"]:
                                index = tool_delta.get("index", 0)
                                
                                # Initialize tool call if not exists
                                if index not in tool_calls:
                                    tool_calls[index] = {
                                        "id": tool_delta.get("id", f"call_{uuid.uuid4().hex}"),
                                        "type": tool_delta.get("type", "function"),
                                        "function": {
                                            "name": tool_delta.get("function", {}).get("name", ""),
                                            "arguments": "",
                                        },
                                        "item_id": f"tool_call_{uuid.uuid4().hex}",
                                        "output_index": tool_call_counter
                                    }
                                    
                                    # If we got a tool name, emit the created event
                                    if "function" in tool_delta and "name" in tool_delta["function"]:
                                        tool_call = tool_calls[index]
                                        tool_call["function"]["name"] = tool_delta["function"]["name"]
                                        
                                        created_event = ToolCallsCreated(
                                            type="response.tool_calls.created",
                                            item_id=tool_call["item_id"],
                                            output_index=tool_call["output_index"],
                                            tool_call={
                                                "id": tool_call["id"],
                                                "type": tool_call["type"],
                                                "function": {
                                                    "name": tool_call["function"]["name"],
                                                    "arguments": ""
                                                }
                                            }
                                        )
                                        
                                        yield f"data: {json.dumps(created_event.dict())}\n\n"
                                        tool_call_counter += 1
                                
                                # Process function arguments if present
                                if "function" in tool_delta and "arguments" in tool_delta["function"]:
                                    arg_fragment = tool_delta["function"]["arguments"]
                                    tool_calls[index]["function"]["arguments"] += arg_fragment
                                    
                                    # Emit delta event
                                    args_event = ToolCallArgumentsDelta(
                                        type="response.tool_calls.arguments.delta",
                                        item_id=tool_calls[index]["item_id"],
                                        output_index=tool_calls[index]["output_index"],
                                        delta=arg_fragment
                                    )
                                    
                                    yield f"data: {json.dumps(args_event.dict())}\n\n"
                        
                        # Handle content (text)
                        elif "content" in delta and delta["content"] is not None:
                            content_delta = delta["content"]
                            
                            # Create a new message if it doesn't exist
                            if not response_obj.output:
                                response_obj.output.append({
                                    "id": message_id,
                                    "type": "message",
                                    "role": "assistant",
                                    "content": []
                                })
                            
                            # Emit text delta event
                            text_event = OutputTextDelta(
                                type="response.output_text.delta",
                                item_id=message_id,
                                output_index=0,
                                delta=content_delta
                            )
                            
                            yield f"data: {json.dumps(text_event.dict())}\n\n"
                    
                    # Check for finish_reason
                    if "finish_reason" in choice and choice["finish_reason"] is not None:
                        # If the finish reason is "tool_calls", emit the arguments.done events
                        if choice["finish_reason"] == "tool_calls":
                            for index, tool_call in tool_calls.items():
                                done_event = ToolCallArgumentsDone(
                                    type="response.tool_calls.arguments.done",
                                    item_id=tool_call["item_id"],
                                    output_index=tool_call["output_index"],
                                    arguments=tool_call["function"]["arguments"]
                                )
                                
                                yield f"data: {json.dumps(done_event.dict())}\n\n"
                                
                                # Update response object with tool call
                                response_obj.output.append({
                                    "id": tool_call["item_id"],
                                    "type": "tool_call",
                                    "function": {
                                        "name": tool_call["function"]["name"],
                                        "arguments": tool_call["function"]["arguments"]
                                    }
                                })
                        
                        # If the finish reason is "stop", emit the completed event
                        if choice["finish_reason"] == "stop":
                            # If we have any text content, add it to the output
                            if not response_obj.output:
                                response_obj.output.append({
                                    "id": message_id,
                                    "type": "message",
                                    "role": "assistant",
                                    "content": [{"type": "output_text", "text": ""}]
                                })
                            
                            response_obj.status = "completed"
                            completed_event = ResponseCompleted(
                                type="response.completed",
                                response=response_obj
                            )
                            
                            yield f"data: {json.dumps(completed_event.dict())}\n\n"
                
            except json.JSONDecodeError:
                logger.error(f"Failed to parse JSON from chunk: {chunk}")
                continue
    
    except Exception as e:
        logger.error(f"Error processing streaming response: {str(e)}")
        # Emit a completion event if we haven't already
        if response_obj.status != "completed":
            response_obj.status = "completed"
            response_obj.error = {"message": str(e)}
            
            completed_event = ResponseCompleted(
                type="response.completed",
                response=response_obj
            )
            
            yield f"data: {json.dumps(completed_event.dict())}\n\n"

# API endpoints
@app.post("/responses")
async def create_response(request: Request):
    """
    Create a response in Responses API format, translating to/from chat.completions API.
    """
    try:
        request_data = await request.json()
        logger.info(f"Received /responses request: {json.dumps(request_data)[:200]}...")
        
        # Convert request to chat.completions format
        chat_request = convert_responses_to_chat_completions(request_data)
        logger.info(f"Converted to chat completions: {json.dumps(chat_request)[:200]}...")
        
        # Check for streaming mode
        stream = request_data.get("stream", False)
        
        if stream:
            # Handle streaming response
            async def stream_response():
                try:
                    async with http_client.stream(
                        "POST",
                        "/v1/chat/completions",
                        json=chat_request,
                        timeout=60.0
                    ) as response:
                        if response.status_code != 200:
                            error_content = await response.aread()
                            logger.error(f"Error from LLM API: {error_content}")
                            yield f"data: {json.dumps({'type': 'error', 'error': {'message': f'Error from LLM API: {response.status_code}'}})}\n\n"
                            return
                        
                        async for event in process_chat_completions_stream(response):
                            yield event
                except Exception as e:
                    logger.error(f"Error in stream_response: {str(e)}")
                    yield f"data: {json.dumps({'type': 'error', 'error': {'message': str(e)}})}\n\n"
            
            return StreamingResponse(
                stream_response(),
                media_type="text/event-stream"
            )
        
        else:
            # Handle non-streaming response
            response = await http_client.post(
                "/v1/chat/completions",
                json=chat_request,
                timeout=60.0
            )
            
            if response.status_code != 200:
                logger.error(f"Error from LLM API: {response.text}")
                raise HTTPException(
                    status_code=response.status_code,
                    detail=f"Error from LLM API: {response.text}"
                )
                
            chat_response = response.json()
            
            # Convert chat.completions response to Responses API format
            response_id = f"resp_{uuid.uuid4().hex}"
            message_id = f"msg_{uuid.uuid4().hex}"
            
            output = []
            
            # Handle potential tool calls
            tool_calls = []
            if "choices" in chat_response and chat_response["choices"]:
                choice = chat_response["choices"][0]
                
                if "message" in choice:
                    message = choice["message"]
                    
                    # Check for tool_calls
                    if "tool_calls" in message and message["tool_calls"]:
                        for i, tool_call in enumerate(message["tool_calls"]):
                            tool_call_id = f"tool_call_{uuid.uuid4().hex}"
                            output.append({
                                "id": tool_call_id,
                                "type": "tool_call",
                                "function": {
                                    "name": tool_call["function"]["name"],
                                    "arguments": tool_call["function"]["arguments"]
                                }
                            })
                    
                    # Check for content
                    if "content" in message and message["content"]:
                        output.append({
                            "id": message_id,
                            "type": "message",
                            "role": "assistant",
                            "content": [{
                                "type": "output_text",
                                "text": message["content"]
                            }]
                        })
            
            responses_response = {
                "id": response_id,
                "object": "response",
                "created_at": current_timestamp(),
                "status": "completed",
                "model": chat_response.get("model", request_data.get("model", "")),
                "output": output,
                "parallel_tool_calls": True,
                "temperature": request_data.get("temperature", 1.0),
                "tool_choice": request_data.get("tool_choice", "auto"),
                "tools": request_data.get("tools", []),
                "top_p": request_data.get("top_p", 1.0),
                "usage": chat_response.get("usage", None)
            }
            
            return responses_response
            
    except Exception as e:
        logger.error(f"Error in create_response: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=f"Error processing request: {str(e)}"
        )

# Health check endpoint
@app.get("/health")
async def health_check():
    return {"status": "ok", "adapter": "running"}

@app.get("/")
async def root():
    return {"message": "API Adapter is running. Use /responses endpoint to interact with the API."}

# Catch-all route to proxy any other requests to the AI provider
@app.api_route("/{path_name:path}", methods=["GET", "POST", "PUT", "DELETE", "OPTIONS", "HEAD", "PATCH", "TRACE"])
async def proxy_endpoint(request: Request, path_name: str):
    """
    Proxy any requests not handled by other routes directly to the AI provider without changes.
    This ensures compatibility with applications that expect the full OpenAI API.
    """
    try:
        # Get the request body if available
        body = await request.body()
        # Get headers but exclude host
        headers = {k.lower(): v for k, v in request.headers.items() if k.lower() != 'host'}
        
        # Make sure we have authorization header
        if 'authorization' not in headers and OPENAI_API_KEY:
            headers['authorization'] = f'Bearer {OPENAI_API_KEY}'
            
        logger.info(f"Proxying request to {path_name}")
        
        # Determine if this is a streaming request
        is_stream = False
        if body:
            try:
                data = json.loads(body)
                is_stream = data.get('stream', False)
            except:
                pass
                
        # Forward the request to the AI provider
        if is_stream:
            # Handle streaming response
            async def stream_proxy():
                try:
                    # Create a client for this specific request
                    async with httpx.AsyncClient(timeout=60.0) as client:
                        async with client.stream(
                            request.method,
                            f"{OPENAI_BASE_URL_INTERNAL}/{path_name}",
                            headers=headers,
                            content=body,
                            timeout=60.0
                        ) as response:
                            if response.status_code != 200:
                                # If there's an error, just return the error response
                                error_content = await response.aread()
                                yield error_content
                                return
                                
                            # Stream the response back
                            async for chunk in response.aiter_bytes():
                                yield chunk
                except Exception as e:
                    logger.error(f"Error in proxy_endpoint streaming: {str(e)}")
                    yield f"Error: {str(e)}".encode('utf-8')
            
            return StreamingResponse(
                stream_proxy(),
                media_type=request.headers.get('accept', 'application/json'),
                status_code=200
            )
        else:
            # Handle regular response
            async with httpx.AsyncClient(timeout=60.0) as client:
                response = await client.request(
                    request.method,
                    f"{OPENAI_BASE_URL_INTERNAL}/{path_name}",
                    headers=headers,
                    content=body,
                    timeout=60.0
                )
                
                # Create the response with the same status code and headers from the proxied response
                return Response(
                    content=response.content,
                    status_code=response.status_code,
                    headers=dict(response.headers)
                )
                
    except Exception as e:
        logger.error(f"Error in proxy_endpoint: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=f"Error proxying request: {str(e)}"
        )

if __name__ == "__main__":
    logger.info(f"Starting API Adapter server on {API_ADAPTER_HOST}:{API_ADAPTER_PORT}")
    logger.info(f"Using OpenAI Base URL (internal): {OPENAI_BASE_URL_INTERNAL}")
    logger.info(f"Using OpenAI Base URL: {OPENAI_BASE_URL}")
    
    uvicorn.run("server:app", host=API_ADAPTER_HOST, port=API_ADAPTER_PORT, reload=True)