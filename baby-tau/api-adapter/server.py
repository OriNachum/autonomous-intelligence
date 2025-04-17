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
OPENAI_BASE_URL = os.getenv("OPENAI_BASE_URL", "http://localhost:8000/v1")
API_ADAPTER_PORT = int(os.getenv("API_ADAPTER_PORT", "8080"))
API_ADAPTER_HOST = os.getenv("API_ADAPTER_HOST", "0.0.0.0")

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
    logger.info(f"Received Chat Completions request for model: {request.model}")
    
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
            response = await client.post(
                f"{OPENAI_BASE_URL}/responses",
                json=responses_request,
                timeout=120.0
            )
            
            response_data = response.json()
            
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
                
                return {
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
                
    except Exception as e:
        logger.error(f"Error forwarding request: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error forwarding request: {str(e)}")

@app.post("/v1/responses")
async def responses(request: ResponseRequest):
    """
    Handle Responses API requests by converting to Chat Completions format
    and forwarding to the actual LLM API.
    """
    logger.info(f"Received Responses request for model: {request.model}")
    
    # Convert input format if it's a string
    if isinstance(request.input, str):
        messages = [{"role": "user", "content": request.input}]
    else:
        messages = request.input
    
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
    
    try:
        # Forward to the actual API
        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{OPENAI_BASE_URL}/chat/completions",
                json=chat_request,
                timeout=120.0
            )
            
            chat_data = response.json()
            
            # Convert Chat Completions format back to Responses format
            if request.stream:
                # Streaming response handling would go here
                return chat_data
            else:
                # Get the content from the first choice
                content = ""
                if chat_data.get("choices") and len(chat_data["choices"]) > 0:
                    content = chat_data["choices"][0].get("message", {}).get("content", "")
                
                # Create a response in Responses format
                return {
                    "id": f"resp_{uuid.uuid4().hex}",
                    "created_at": chat_data.get("created", int(uuid.uuid1().time // 10**6)),
                    "model": request.model,
                    "content": [
                        {
                            "type": "output_text",
                            "text": content,
                            "annotations": []
                        }
                    ],
                    "output_text": content,
                    "usage": chat_data.get("usage", {
                        "prompt_tokens": 0,
                        "completion_tokens": 0,
                        "total_tokens": 0
                    })
                }
                
    except Exception as e:
        logger.error(f"Error forwarding request: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error forwarding request: {str(e)}")

# Proxy all other requests unchanged
@app.api_route("/{path:path}", methods=["GET", "POST", "PUT", "DELETE", "OPTIONS", "HEAD", "PATCH"])
async def proxy(request: Request, path: str):
    """
    Proxy all other requests to the actual API unchanged.
    """
    try:
        # Get the target URL
        target_url = f"{OPENAI_BASE_URL}/{path}"
        
        # Get request details
        method = request.method
        headers = dict(request.headers)
        params = dict(request.query_params)
        
        # Remove headers that might cause issues
        headers.pop("host", None)
        
        # Get the request body
        body = await request.body()
        
        async with httpx.AsyncClient() as client:
            # Forward the request
            response = await client.request(
                method=method,
                url=target_url,
                params=params,
                headers=headers,
                content=body,
                timeout=120.0
            )
            
            # Return the response
            return response.json()
    except Exception as e:
        logger.error(f"Error proxying request: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error proxying request: {str(e)}")

if __name__ == "__main__":
    logger.info(f"Starting API adapter server on {API_ADAPTER_HOST}:{API_ADAPTER_PORT}")
    uvicorn.run(app, host=API_ADAPTER_HOST, port=API_ADAPTER_PORT)
