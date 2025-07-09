import os
import json
import time
import base64
from typing import List, Dict, Optional, AsyncGenerator, Union
from contextlib import asynccontextmanager
from io import BytesIO

from fastapi import FastAPI, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from PIL import Image
import uvicorn

from model_handler import ModelHandler


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


class ChatCompletionResponse(BaseModel):
    id: str
    object: str = "chat.completion"
    created: int
    model: str
    choices: List[Dict]
    usage: Dict[str, int]


class ModelInfo(BaseModel):
    id: str
    object: str = "model"
    created: int
    owned_by: str = "gemma3n"


model_handler: Optional[ModelHandler] = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    global model_handler
    model_handler = ModelHandler()
    yield
    del model_handler


app = FastAPI(title="Gemma3n API Server", lifespan=lifespan)


def extract_text_and_images(messages: List[Message]) -> tuple[str, Optional[Image.Image]]:
    """Extract text content and first image from messages."""
    text_parts = []
    image = None
    
    for message in messages:
        if isinstance(message.content, str):
            text_parts.append(f"{message.role}: {message.content}")
        elif isinstance(message.content, list):
            for item in message.content:
                if isinstance(item, dict):
                    if item.get("type") == "text":
                        text_parts.append(f"{message.role}: {item.get('text', '')}")
                    elif item.get("type") == "image_url":
                        if image is None:  # Only take the first image
                            image_data = item.get("image_url", {})
                            if isinstance(image_data, dict):
                                image_url = image_data.get("url", "")
                                if image_url.startswith("data:image"):
                                    # Extract base64 data
                                    base64_data = image_url.split(",")[1]
                                    image_bytes = base64.b64decode(base64_data)
                                    image = Image.open(BytesIO(image_bytes))
    
    return "\n".join(text_parts), image


async def generate_stream_response(
    request_id: str,
    model: str,
    prompt: str,
    image: Optional[Image.Image],
    generation_params: Dict
) -> AsyncGenerator[str, None]:
    """Generate streaming response in OpenAI format."""
    
    # Stream the generated tokens
    async for token in model_handler.generate_stream(prompt, image, generation_params):
        chunk = {
            "id": request_id,
            "object": "chat.completion.chunk",
            "created": int(time.time()),
            "model": model,
            "choices": [{
                "index": 0,
                "delta": {"content": token},
                "finish_reason": None
            }]
        }
        yield f"data: {json.dumps(chunk)}\n\n"
    
    # Send the final chunk
    final_chunk = {
        "id": request_id,
        "object": "chat.completion.chunk",
        "created": int(time.time()),
        "model": model,
        "choices": [{
            "index": 0,
            "delta": {},
            "finish_reason": "stop"
        }]
    }
    yield f"data: {json.dumps(final_chunk)}\n\n"
    yield "data: [DONE]\n\n"


@app.post("/v1/chat/completions")
async def chat_completions(request: ChatCompletionRequest):
    """OpenAI-compatible chat completions endpoint."""
    
    if model_handler is None:
        raise HTTPException(status_code=503, detail="Model not loaded")
    
    # Extract text and images from messages
    prompt, image = extract_text_and_images(request.messages)
    
    # Prepare generation parameters
    generation_params = {
        "temperature": request.temperature,
        "max_new_tokens": request.max_tokens,
        "top_p": request.top_p,
    }
    
    request_id = f"chatcmpl-{int(time.time() * 1000)}"
    
    if request.stream:
        return StreamingResponse(
            generate_stream_response(request_id, request.model, prompt, image, generation_params),
            media_type="text/event-stream"
        )
    else:
        # Non-streaming response
        response_text = await model_handler.generate(prompt, image, generation_params)
        
        response = ChatCompletionResponse(
            id=request_id,
            created=int(time.time()),
            model=request.model,
            choices=[{
                "index": 0,
                "message": {
                    "role": "assistant",
                    "content": response_text
                },
                "finish_reason": "stop"
            }],
            usage={
                "prompt_tokens": len(prompt.split()),  # Approximate
                "completion_tokens": len(response_text.split()),  # Approximate
                "total_tokens": len(prompt.split()) + len(response_text.split())
            }
        )
        
        return response


@app.get("/v1/models")
async def list_models():
    """List available models."""
    return {
        "object": "list",
        "data": [
            ModelInfo(
                id="gemma3n",
                created=int(time.time()),
                owned_by="google"
            )
        ]
    }


@app.get("/health")
async def health_check():
    """Health check endpoint."""
    return {
        "status": "healthy",
        "model_loaded": model_handler is not None
    }


if __name__ == "__main__":
    port = int(os.getenv("PORT", "8000"))
    uvicorn.run(app, host="0.0.0.0", port=port)