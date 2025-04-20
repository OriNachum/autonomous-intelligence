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
import traceback
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Configure logging with more focused format
logging.basicConfig(
    level=logging.INFO,  # Keep at INFO level for important logs only
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    # Both console and logfile at ./log folder

    handlers=[
        logging.FileHandler("./log/api_adapter.log"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger("api_adapter")

# Configuration from environment variables
OPENAI_BASE_URL_INTERNAL = os.environ.get("OPENAI_BASE_URL_INTERNAL", "http://localhost:8000")
OPENAI_BASE_URL = os.environ.get("OPENAI_BASE_URL", "http://localhost:8080")
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY", "dummy-key")
API_ADAPTER_HOST = os.environ.get("API_ADAPTER_HOST", "0.0.0.0")
API_ADAPTER_PORT = int(os.environ.get("API_ADAPTER_PORT", "8080"))

logger.info(f"Configuration: OPENAI_BASE_URL_INTERNAL={OPENAI_BASE_URL_INTERNAL}, API_PORT={API_ADAPTER_PORT}")

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
    base_url=OPENAI_BASE_URL_INTERNAL,  # Fixed: using the actual variable
    headers={"Authorization": f"Bearer {OPENAI_API_KEY}"},
    timeout=httpx.Timeout(120.0)  # Increased timeout
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
    type: str = "response.function_call_arguments.delta"
    item_id: str
    output_index: int
    delta: str

class ToolCallArgumentsDone(BaseModel):
    type: str = "response.function_call_arguments.done"
    id: str
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
    logger = logging.getLogger("api_adapter_conversion")
    # Log only essential info - model, tools count, if instructions present
    logger.info(f"Request: model={request_data.get('model')}, " +
                f"tools={len(request_data.get('tools', []))}, " +
                f"has_instructions={'instructions' in request_data}")
    logger.info(f"Tools in request={request_data.get('tools', [])}")
    
    chat_request = {
        "model": request_data.get("model"),
        "temperature": request_data.get("temperature", 1.0),
        "top_p": request_data.get("top_p", 1.0),
        "stream": request_data.get("stream", False),
    }

    # Handle instructions (specific to Codex)
    if "instructions" in request_data:
        chat_request["system"] = request_data["instructions"]

    # Convert any max_output_tokens to max_tokens
    if "max_output_tokens" in request_data:
        chat_request["max_tokens"] = request_data["max_output_tokens"]

    # Convert input to messages
    messages = []
    
    # Check for system message first if we have instructions
    if "instructions" in request_data:
        messages.append({"role": "system", "content": request_data["instructions"]})
    
    # Check for previous tool responses in the input
    if "input" in request_data and request_data["input"]:
        user_message = {"role": "user", "content": ""}
        logger.info(f"Processing input messages {request_data['input']}")
        for i, item in enumerate(request_data["input"]):
            if isinstance(item, dict):
                if item.get("type") == "message" and item.get("role") == "user":
                    # Add user message
                    content = ""
                    if "content" in item:
                        for j, content_item in enumerate(item["content"]):
                            if isinstance(content_item, dict) and content_item.get("type") == "input_text":
                                content = content_item.get("text", "")
                    user_message = {"role": "user", "content": content}
                    messages.append(user_message)
                    # Log user message content for context
                    logger.info(f"User message: {content[:100]}...")
                    
                elif item.get("type") == "function_call_output":
                    # Add tool output - log tool usage
                    logger.info(f"Tool response: call_id={item.get('call_id')}, output={item.get('output', '')[:50]}...")
                    tool_message = {
                        "role": "tool",
                        "tool_call_id": item.get("call_id"),
                        "content": item.get("output", "")
                    }
                    messages.append(tool_message)
            elif isinstance(item, str):
                # Simple string input
                messages.append({"role": "user", "content": item})
                logger.info(f"User message (string): {item[:100]}...")
    
    # If we only have a system message or no messages at all, add an empty user message
    if not messages or (len(messages) == 1 and messages[0]["role"] == "system"):
        messages.append({"role": "user", "content": ""})
    
    chat_request["messages"] = messages

    # Convert tools - log each tool being processed
    if "tools" in request_data and request_data["tools"]:
        chat_request["tools"] = []
        
        for i, tool in enumerate(request_data["tools"]):
            try:
                logger.info(f"Trying to convert tool {i}: {tool}")
                if not isinstance(tool, dict) or "type" not in tool or tool.get("type") != "function":
                    continue
                    
                function_obj = tool
                if not isinstance(function_obj, dict) or "name" not in function_obj:
                    continue
                
                function_data = {
                    "name": function_obj["name"],
                }
                
                # Log tool information
                logger.info(f"Converting Tool {i}: {function_data['name']}")
                
                if "description" in function_obj:
                    function_data["description"] = function_obj["description"]
                    
                if "parameters" in function_obj:
                    function_data["parameters"] = function_obj["parameters"]
                
                chat_request["tools"].append({
                    "type": "function",
                    "function": function_data
                })
            except Exception as e:
                logger.error(f"Error processing tool {i}: {str(e)}")
    
    # Handle tool_choice
    if "tool_choice" in request_data:
        chat_request["tool_choice"] = request_data["tool_choice"]
    
    # Add optional parameters if they exist
    for key in ["user", "metadata"]:
        if key in request_data and request_data[key] is not None:
            chat_request[key] = request_data[key]
    
    logger.info(f"Converted to chat completions: {len(messages)} messages, {len(chat_request.get('tools', []))} tools")
    return chat_request

async def process_chat_completions_stream(response):
    """
    Process the streaming response from chat.completions API.
    Tracks the state of tool calls to properly convert them to Responses API events.
    """
    logger = logging.getLogger("api_adapter_stream")
    tool_calls = {}  # Store tool calls being built
    response_id = f"resp_{uuid.uuid4().hex}"
    tool_call_counter = 0
    message_id = f"msg_{uuid.uuid4().hex}"
    output_text_content = ""  # Track the full text content for logging
    logger.info(f"Processing streaming response from chat.completions API response_id {response_id}; message_id {message_id}")
    
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
    logger.info(f"Emitting {created_event}")
    yield f"data: {json.dumps(created_event.dict())}\n\n"
    
    # Also emit the in_progress event
    in_progress_event = ResponseInProgress(
        type="response.in_progress",
        response=response_obj
    )
    
    logger.info(f"Emitting {in_progress_event}")
    yield f"data: {json.dumps(in_progress_event.dict())}\n\n"
    
    chunk_counter = 0
    try:
        async for chunk in response.aiter_lines():
            chunk_counter += 1
            if not chunk.strip():
                continue
            logger.info(chunk)
                
            # Handle [DONE] message
            if chunk.strip() == "data: [DONE]" or chunk.strip() == "[DONE]":
                logger.info(f"Received [DONE] message after {chunk_counter} chunks")
                
                # If we haven't already completed the response, do it now
                if response_obj.status != "completed":
                    # If no output, add empty message
                    if not response_obj.output:
                        response_obj.output.append({
                            "id": message_id,
                            "type": "message",
                            "role": "assistant",
                            "content": [{"type": "output_text", "text": output_text_content or ""}]
                        })
                    
                    response_obj.status = "completed"
                    completed_event = ResponseCompleted(
                        type="response.completed",
                        response=response_obj
                    )
                    
                    yield f"data: {json.dumps(completed_event.dict())}\n\n"
                continue
                
            # Skip prefix if present
            if chunk.startswith("data: "):
                chunk = chunk[6:]
                
            try:
                data = json.loads(chunk)
                logger.info(f"data: {data}")
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
                            logger.info(f"tool_calls in {delta}")

                            for tool_delta in delta["tool_calls"]:
                                index = tool_delta.get("index", 0)
                                
                                # Initialize tool call if not exists
                                if index not in tool_calls:
                                    tool_calls[index] = {
                                        "id": tool_delta.get("id", f"call_{uuid.uuid4().hex}"),
                                        "type": tool_delta.get("type", "function"),
                                        "function": {
                                            "name": tool_delta.get("function", {}).get("name", ""),
                                            "arguments": tool_delta.get("function", {}).get("arguments", ""),
                                        },
                                        "item_id": f"tool_call_{uuid.uuid4().hex}",
                                        "output_index": tool_call_counter
                                    }
                                    
                                    # If we got a tool name, emit the created event
                                    if "function" in tool_delta and "name" in tool_delta["function"]:
                                        tool_call = tool_calls[index]
                                        tool_call["function"]["name"] = tool_delta["function"]["name"]
                                        # Log tool call creation
                                        logger.info(f"Tool call created: {tool_call['function']['name']}")
                                        # {'role': 'assistant', 'content': '', 'tool_calls': [{'id': 'call_ceizcjxw', 'index': 0, 'type': 'function', 'function': {'name': 'apply_patch', 'arguments': '{"cmd":"[\\"apply_patch\\", \\"*** Begin Patch\\\\n*** Update File: path/to/file.py\\\\n@@ def example():\\\\n-  pass\\\\n+  return 123\\\\n*** End Patch\\"]"}'}}]}, 'finish_reason': None}]}

                                        response_obj.output.append({
                                            "arguments": tool_call["function"]["arguments"],
                                            "call_id": tool_call["id"],
                                            "name": tool_call["function"]["name"],
                                            "type": "function_call",
                                            "id": tool_call["id"],
                                            "status": "in_progress"
                                        })
                                        # Also emit the in_progress event
                                        in_progress_event = ResponseInProgress(
                                            type="response.in_progress",
                                            response=response_obj
                                        )
                                        
                                        logger.info(f"Emitting {in_progress_event}")
                                        yield f"data: {json.dumps(in_progress_event.dict())}\n\n"


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
                                        type="response.function_call_arguments.delta",
                                        item_id=tool_calls[index]["item_id"],
                                        output_index=tool_calls[index]["output_index"],
                                        delta=arg_fragment
                                    )
                                    
                                    yield f"data: {json.dumps(args_event.dict())}\n\n"
                        
                        # Handle content (text)
                        elif "content" in delta and delta["content"] is not None:
                            content_delta = delta["content"]
                            output_text_content += content_delta
                            
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
                        logger.info(f"Received finish_reason: {choice['finish_reason']}")
                        
                        # If the finish reason is "tool_calls", emit the arguments.done events
                        if choice["finish_reason"] == "tool_calls":
                            for index, tool_call in tool_calls.items():
                                # Log the complete tool call arguments
                                logger.info(f"Tool call completed: {tool_call['function']['name']} with arguments: {tool_call['function']['arguments']}")
                                
                                done_event = ToolCallArgumentsDone(
                                    type="response.function_call_arguments.done",
                                    id=tool_call["item_id"],
                                    #=f'{tool_call["item_id"]}_{uuid.uuid().hex}',
                                    output_index=tool_call["output_index"],
                                    arguments=tool_call["function"]["arguments"]
                                )
                                logger.info(f"Emitting {done_event}")
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
                                    "content": [{"type": "output_text", "text": output_text_content or ""}]
                                })
                            
                            # Log complete output text
                            logger.info(f"Response completed with text: {output_text_content[:100]}...")
                                
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
        logger = logging.getLogger("api_adapter_responses")
        logger.info("Received request to /responses")
        request_data = await request.json()
        
        # Log basic request information
        logger.info(f"Received request: model={request_data.get('model')}, stream={request_data.get('stream')}")
        
        # Log input content for better visibility
        if "input" in request_data and request_data["input"]:
            logger.info("==== REQUEST CONTENT ====")
            #     "input": [{"role": "user", "content": [{"type": "input_text", "text": "save a file with \"demo2\" text called \"demo2.md\""}], "type": "message"}],
            for i, item in enumerate(request_data["input"]):
                if isinstance(item, dict):
                    if item.get("type") == "message" and item.get("role") == "user":
                        if "content" in item and isinstance(item["content"], list):
                            for index, content_item in enumerate(item["content"]):
                                if isinstance(content_item, dict):
                                    # Handle nested content structure like {"type": "input_text", "text": "actual message"}
                                    if content_item.get("type") == "input_text" and "text" in content_item:
                                        user_text = content_item.get("text", "")
                                        logger.info(f"USER INPUT: {user_text}")
                                    elif content_item.get("type") == "text" and "text" in content_item:
                                        user_text = content_item.get("text", "")
                                        logger.info(f"USER INPUT: {user_text}")
                                    # Handle other content types
                                    elif "type" in content_item:
                                        logger.info(f"USER INPUT ({content_item.get('type')}): {str(content_item)[:100]}...")
                                elif isinstance(content_item, str):
                                    logger.info(f"USER INPUT: {content_item}")
                    elif item.get("type") == "function_call_output":
                        logger.info(f"FUNCTION RESULT: call_id={item.get('call_id')}, output={str(item.get('output', ''))[:100]}...")
                elif isinstance(item, str):
                    logger.info(f"USER INPUT: {item}")
            logger.info("=======================")
        
        # Convert request to chat.completions format
        chat_request = convert_responses_to_chat_completions(request_data)
        
        # Check for streaming mode
        stream = request_data.get("stream", False)
        
        if stream:
            logger.info("Handling streaming response")
            # Handle streaming response
            async def stream_response():
                try:
                    chat_request['functions'] = chat_request['tools']
                    logger.info(f"Sending tools: {chat_request['tools']}")
                    async with http_client.stream(
                        "POST",
                        "/v1/chat/completions",
                        json=chat_request,
                        timeout=120.0
                    ) as response:
                        logger.info(f"Stream request status: {response.status_code}")
                        
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
            logger.info("Non-streaming response unsupported")
            
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
        logger = logging.getLogger("api_adapter_proxy")
        logger.info(f"Proxying request to {path_name}")

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
                            f"{OPENAI_BASE_URL_INTERNAL}/v1/{path_name}",  # Add /v1 here
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
                    f"{OPENAI_BASE_URL_INTERNAL}/v1/{path_name}",  # Add /v1 here
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