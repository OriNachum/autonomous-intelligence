from fastapi import FastAPI, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from typing import List, Optional, Union, Dict, Any
import tritonclient.http as httpclient
import tritonclient.grpc as grpcclient
import numpy as np
import json
import asyncio
import uuid
from datetime import datetime
import os
import logging
import base64

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(title="Gemma-Triton OpenAI API", version="1.0.0")

# Triton server configuration
TRITON_HTTP_URL = os.environ.get("TRITON_HTTP_URL", "localhost:8000")
TRITON_GRPC_URL = os.environ.get("TRITON_GRPC_URL", "localhost:8001")
MODEL_NAME = "gemma3n"
MODEL_VERSION = "1"

# Initialize Triton clients
http_client = httpclient.InferenceServerClient(url=TRITON_HTTP_URL)
grpc_client = grpcclient.InferenceServerClient(url=TRITON_GRPC_URL)

# OpenAI API Models
class Message(BaseModel):
    role: str
    content: Union[str, List[Dict[str, Any]]]

class ChatCompletionRequest(BaseModel):
    model: str
    messages: List[Message]
    temperature: Optional[float] = 0.7
    max_tokens: Optional[int] = 512
    top_p: Optional[float] = 0.9
    frequency_penalty: Optional[float] = 0.0
    presence_penalty: Optional[float] = 0.0
    stream: Optional[bool] = False
    n: Optional[int] = 1

class ChatCompletionChoice(BaseModel):
    index: int
    message: Message
    finish_reason: str

class ChatCompletionResponse(BaseModel):
    id: str
    object: str = "chat.completion"
    created: int
    model: str
    choices: List[ChatCompletionChoice]
    usage: Dict[str, int]

class Model(BaseModel):
    id: str
    object: str = "model"
    created: int
    owned_by: str = "triton"

class ModelsResponse(BaseModel):
    object: str = "list"
    data: List[Model]

def format_messages_to_prompt(messages: List[Message]) -> tuple[str, List[str]]:
    """Convert OpenAI messages format to a single prompt and extract images"""
    prompt_parts = []
    images = []
    
    for message in messages:
        role = message.role
        
        if isinstance(message.content, str):
            # Simple text content
            if role == "system":
                prompt_parts.append(f"System: {message.content}")
            elif role == "user":
                prompt_parts.append(f"User: {message.content}")
            elif role == "assistant":
                prompt_parts.append(f"Assistant: {message.content}")
        else:
            # Complex content with potential images
            text_parts = []
            for content_item in message.content:
                if content_item["type"] == "text":
                    text_parts.append(content_item["text"])
                elif content_item["type"] == "image_url":
                    image_url = content_item["image_url"]["url"]
                    # Extract base64 image data
                    if image_url.startswith("data:image"):
                        base64_data = image_url.split(",")[1]
                        images.append(base64_data)
                        text_parts.append("<image>")
            
            combined_text = " ".join(text_parts)
            if role == "system":
                prompt_parts.append(f"System: {combined_text}")
            elif role == "user":
                prompt_parts.append(f"User: {combined_text}")
            elif role == "assistant":
                prompt_parts.append(f"Assistant: {combined_text}")
    
    # Add final assistant prompt
    prompt_parts.append("Assistant:")
    
    return "\n\n".join(prompt_parts), images

async def call_triton_model(prompt: str, images: List[str], max_tokens: int, 
                          temperature: float, top_p: float, stream: bool = False):
    """Call Triton inference server"""
    try:
        # Prepare inputs
        inputs = []
        
        # Prompt input
        prompt_input = httpclient.InferInput("prompt", [1], "BYTES")
        prompt_input.set_data_from_numpy(np.array([prompt.encode('utf-8')], dtype=np.object_))
        inputs.append(prompt_input)
        
        # Images input (optional)
        if images:
            images_input = httpclient.InferInput("images", [len(images)], "BYTES")
            images_data = np.array([img.encode('utf-8') for img in images], dtype=np.object_)
            images_input.set_data_from_numpy(images_data)
            inputs.append(images_input)
        
        # Max tokens input
        max_tokens_input = httpclient.InferInput("max_tokens", [1], "INT32")
        max_tokens_input.set_data_from_numpy(np.array([max_tokens], dtype=np.int32))
        inputs.append(max_tokens_input)
        
        # Temperature input
        temperature_input = httpclient.InferInput("temperature", [1], "FP32")
        temperature_input.set_data_from_numpy(np.array([temperature], dtype=np.float32))
        inputs.append(temperature_input)
        
        # Top-p input
        top_p_input = httpclient.InferInput("top_p", [1], "FP32")
        top_p_input.set_data_from_numpy(np.array([top_p], dtype=np.float32))
        inputs.append(top_p_input)
        
        # Stream input
        stream_input = httpclient.InferInput("stream", [1], "BOOL")
        stream_input.set_data_from_numpy(np.array([stream], dtype=bool))
        inputs.append(stream_input)
        
        # Prepare outputs
        outputs = [httpclient.InferRequestedOutput("text")]
        
        # Make inference request
        response = http_client.infer(
            model_name=MODEL_NAME,
            model_version=MODEL_VERSION,
            inputs=inputs,
            outputs=outputs
        )
        
        # Get output
        output_data = response.as_numpy("text")
        text = output_data[0].decode('utf-8')
        
        return text
        
    except Exception as e:
        logger.error(f"Triton inference error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/health")
async def health_check():
    """Health check endpoint"""
    try:
        # Check if Triton server is responsive
        if http_client.is_server_live():
            # Check if model is ready
            if http_client.is_model_ready(MODEL_NAME, MODEL_VERSION):
                return {"status": "healthy", "model": MODEL_NAME, "version": MODEL_VERSION}
            else:
                return {"status": "unhealthy", "error": "Model not ready"}
        else:
            return {"status": "unhealthy", "error": "Triton server not responsive"}
    except Exception as e:
        return {"status": "unhealthy", "error": str(e)}

@app.get("/v1/models", response_model=ModelsResponse)
async def list_models():
    """List available models"""
    return ModelsResponse(
        data=[
            Model(
                id=MODEL_NAME,
                created=int(datetime.now().timestamp()),
                owned_by="triton"
            )
        ]
    )

@app.post("/v1/chat/completions")
async def chat_completions(request: ChatCompletionRequest):
    """OpenAI-compatible chat completions endpoint"""
    
    # Convert messages to prompt and extract images
    prompt, images = format_messages_to_prompt(request.messages)
    
    # Call Triton model
    response_text = await call_triton_model(
        prompt=prompt,
        images=images,
        max_tokens=request.max_tokens,
        temperature=request.temperature,
        top_p=request.top_p,
        stream=request.stream
    )
    
    if request.stream:
        # Streaming response
        async def generate_stream():
            # Split response into chunks for streaming
            words = response_text.split()
            chunk_size = 3  # Words per chunk
            
            for i in range(0, len(words), chunk_size):
                chunk_words = words[i:i + chunk_size]
                chunk_text = " ".join(chunk_words)
                if i + chunk_size < len(words):
                    chunk_text += " "
                
                chunk_data = {
                    "id": f"chatcmpl-{uuid.uuid4().hex}",
                    "object": "chat.completion.chunk",
                    "created": int(datetime.now().timestamp()),
                    "model": request.model,
                    "choices": [{
                        "index": 0,
                        "delta": {"content": chunk_text},
                        "finish_reason": None
                    }]
                }
                
                yield f"data: {json.dumps(chunk_data)}\n\n"
                await asyncio.sleep(0.01)  # Small delay for streaming effect
            
            # Final chunk
            final_chunk = {
                "id": f"chatcmpl-{uuid.uuid4().hex}",
                "object": "chat.completion.chunk",
                "created": int(datetime.now().timestamp()),
                "model": request.model,
                "choices": [{
                    "index": 0,
                    "delta": {},
                    "finish_reason": "stop"
                }]
            }
            yield f"data: {json.dumps(final_chunk)}\n\n"
            yield "data: [DONE]\n\n"
        
        return StreamingResponse(
            generate_stream(),
            media_type="text/event-stream"
        )
    else:
        # Non-streaming response
        completion_id = f"chatcmpl-{uuid.uuid4().hex}"
        created_time = int(datetime.now().timestamp())
        
        # Estimate token usage (rough approximation)
        prompt_tokens = len(prompt.split()) * 1.3
        completion_tokens = len(response_text.split()) * 1.3
        
        return ChatCompletionResponse(
            id=completion_id,
            created=created_time,
            model=request.model,
            choices=[
                ChatCompletionChoice(
                    index=0,
                    message=Message(role="assistant", content=response_text),
                    finish_reason="stop"
                )
            ],
            usage={
                "prompt_tokens": int(prompt_tokens),
                "completion_tokens": int(completion_tokens),
                "total_tokens": int(prompt_tokens + completion_tokens)
            }
        )

if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("API_PORT", "8080"))
    uvicorn.run(app, host="0.0.0.0", port=port)