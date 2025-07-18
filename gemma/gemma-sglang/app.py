#!/usr/bin/env python3

import asyncio
import json
import logging
import time
import uuid
from typing import AsyncGenerator, Dict, List, Optional, Union, Any

import uvicorn
from fastapi import FastAPI, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from model_handler import SGLangGemmaHandler

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(
    title="Gemma 3n SGLang API",
    description="OpenAI-compatible API for Gemma 3n multimodal model using SGLang",
    version="1.0.0"
)

# Global model handler
model_handler: Optional[SGLangGemmaHandler] = None

# OpenAI-compatible data models
class Message(BaseModel):
    role: str
    content: Union[str, List[Dict[str, Union[str, Dict[str, str]]]]]

class ChatCompletionRequest(BaseModel):
    model: str = "gemma3n"
    messages: List[Message]
    temperature: Optional[float] = Field(default=0.7, ge=0.0, le=2.0)
    max_tokens: Optional[int] = Field(default=2048, ge=1)
    stream: Optional[bool] = False
    top_p: Optional[float] = Field(default=1.0, ge=0.0, le=1.0)
    frequency_penalty: Optional[float] = Field(default=0.0, ge=-2.0, le=2.0)
    presence_penalty: Optional[float] = Field(default=0.0, ge=-2.0, le=2.0)
    stop: Optional[Union[str, List[str]]] = None

class Usage(BaseModel):
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int

class Choice(BaseModel):
    index: int
    message: Message
    finish_reason: str

class ChatCompletionResponse(BaseModel):
    id: str
    object: str = "chat.completion"
    created: int
    model: str
    choices: List[Choice]
    usage: Usage

class StreamChoice(BaseModel):
    index: int
    delta: Dict[str, Any]
    finish_reason: Optional[str] = None

class ChatCompletionStreamResponse(BaseModel):
    id: str
    object: str = "chat.completion.chunk"
    created: int
    model: str
    choices: List[StreamChoice]

class Model(BaseModel):
    id: str
    object: str = "model"
    created: int
    owned_by: str

class ModelList(BaseModel):
    object: str = "list"
    data: List[Model]

@app.on_event("startup")
async def startup_event():
    """Initialize the model handler on startup."""
    global model_handler
    logger.info("Initializing SGLang Gemma 3n model...")
    try:
        model_handler = SGLangGemmaHandler()
        await model_handler.initialize()
        logger.info("Model initialization complete")
    except Exception as e:
        logger.error(f"Failed to initialize model: {e}")
        raise

@app.on_event("shutdown")
async def shutdown_event():
    """Cleanup on shutdown."""
    global model_handler
    if model_handler:
        await model_handler.cleanup()

@app.get("/health")
async def health_check():
    """Health check endpoint."""
    if model_handler is None or not model_handler.is_ready():
        raise HTTPException(status_code=503, detail="Model not ready")
    return {"status": "healthy", "model": "gemma3n"}

@app.get("/v1/models", response_model=ModelList)
async def list_models():
    """List available models."""
    return ModelList(
        data=[
            Model(
                id="gemma3n",
                created=int(time.time()),
                owned_by="sglang"
            )
        ]
    )

@app.post("/v1/chat/completions")
async def create_chat_completion(request: ChatCompletionRequest):
    """Create a chat completion, either streaming or non-streaming."""
    if model_handler is None:
        raise HTTPException(status_code=503, detail="Model not ready")

    request_id = f"chatcmpl-{uuid.uuid4().hex[:8]}"
    created_time = int(time.time())

    try:
        if request.stream:
            return StreamingResponse(
                generate_stream_response(request, request_id, created_time),
                media_type="text/plain"
            )
        else:
            return await generate_completion_response(request, request_id, created_time)
    except Exception as e:
        logger.error(f"Error processing request: {e}")
        raise HTTPException(status_code=500, detail=str(e))

async def generate_completion_response(
    request: ChatCompletionRequest, 
    request_id: str, 
    created_time: int
) -> ChatCompletionResponse:
    """Generate a non-streaming completion response."""
    
    # Process messages and extract multimodal content
    processed_input = await process_messages(request.messages)
    
    # Generate response using SGLang
    response_text, usage_info = await model_handler.generate(
        processed_input,
        temperature=request.temperature,
        max_tokens=request.max_tokens,
        top_p=request.top_p,
        stop=request.stop
    )
    
    return ChatCompletionResponse(
        id=request_id,
        created=created_time,
        model=request.model,
        choices=[
            Choice(
                index=0,
                message=Message(role="assistant", content=response_text),
                finish_reason="stop"
            )
        ],
        usage=Usage(
            prompt_tokens=usage_info.get("prompt_tokens", 0),
            completion_tokens=usage_info.get("completion_tokens", 0),
            total_tokens=usage_info.get("total_tokens", 0)
        )
    )

async def generate_stream_response(
    request: ChatCompletionRequest,
    request_id: str,
    created_time: int
) -> AsyncGenerator[str, None]:
    """Generate a streaming completion response."""
    
    # Process messages and extract multimodal content
    processed_input = await process_messages(request.messages)
    
    # Generate streaming response using SGLang
    async for token, finish_reason in model_handler.generate_stream(
        processed_input,
        temperature=request.temperature,
        max_tokens=request.max_tokens,
        top_p=request.top_p,
        stop=request.stop
    ):
        chunk = ChatCompletionStreamResponse(
            id=request_id,
            created=created_time,
            model=request.model,
            choices=[
                StreamChoice(
                    index=0,
                    delta={"content": token} if token else {},
                    finish_reason=finish_reason
                )
            ]
        )
        yield f"data: {chunk.model_dump_json()}\n\n"
    
    # Send final chunk
    yield "data: [DONE]\n\n"

async def process_messages(messages: List[Message]) -> Dict[str, Any]:
    """Process messages to extract text, images, and audio content."""
    processed_content = {
        "text": "",
        "images": [],
        "audio": []
    }
    
    for message in messages:
        if isinstance(message.content, str):
            # Simple text message
            processed_content["text"] += f"{message.role}: {message.content}\n"
        elif isinstance(message.content, list):
            # Multimodal message
            for content_item in message.content:
                if content_item.get("type") == "text":
                    processed_content["text"] += f"{message.role}: {content_item.get('text', '')}\n"
                elif content_item.get("type") == "image_url":
                    image_data = content_item.get("image_url", {})
                    processed_content["images"].append(image_data)
                elif content_item.get("type") == "audio":
                    audio_data = content_item.get("audio", {})
                    processed_content["audio"].append(audio_data)
    
    return processed_content

if __name__ == "__main__":
    import os
    
    host = os.getenv("HOST", "0.0.0.0")
    port = int(os.getenv("PORT", 8080))
    
    uvicorn.run(
        "app:app",
        host=host,
        port=port,
        reload=False,
        access_log=True
    )