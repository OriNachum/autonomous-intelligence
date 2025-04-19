"""
Handler for the Responses API endpoints.
"""

import time
import httpx
from fastapi import Request, HTTPException
from fastapi.responses import StreamingResponse
from typing import Dict, Any

from models.requests import ResponseRequest
from utils import (
    generate_request_id, 
    log_request_response, 
    log_request_details,
    process_input_messages,
    convert_to_chat_request,
    create_basic_response
)
from stream_processor import stream_generator
from config import OPENAI_BASE_URL_STRIPPED, REQUEST_TIMEOUT, logger

async def handle_responses(request: ResponseRequest, raw_request: Request):
    """
    Handle Responses API requests by converting to Chat Completions format
    and forwarding to the actual LLM API.
    """
    request_id = generate_request_id()
    await log_request_details(request_id, raw_request)
    logger.info(f"[{request_id}] Received Responses request for model: {request.model}")
    
    # Process input messages
    messages = process_input_messages(request.input, request_id)
    
    # Convert to chat completions format
    chat_request = convert_to_chat_request(messages, request, request_id)
    
    try:
        # Forward to the chat completions API endpoint
        async with httpx.AsyncClient() as client:
            logger.info(f"[{request_id}] Sending request to {OPENAI_BASE_URL_STRIPPED}/v1/chat/completions")
            start_time = time.time()
            
            try:
                response = await client.post(
                    f"{OPENAI_BASE_URL_STRIPPED}/v1/chat/completions",
                    json=chat_request,
                    timeout=REQUEST_TIMEOUT
                )
                end_time = time.time()
                logger.info(f"[{request_id}] API request completed in {end_time - start_time:.2f}s with status {response.status_code}")
                
                # Check for errors
                if response.status_code != 200:
                    logger.error(f"API returned status {response.status_code}: {response.text}")
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
            
            # Handle streaming vs non-streaming responses
            if request.stream:
                logger.info(f"[{request_id}] Streaming response back to client")
                return StreamingResponse(
                    content=stream_generator(
                        response, 
                        request.model, 
                        request_id, 
                        request.store, 
                        request.temperature, 
                        request.top_p
                    ),
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
                logger.info(f"[{request_id}] Parsed response JSON: {chat_data}")
                
                # Get the content from the first choice
                content = ""
                if chat_data.get("choices") and len(chat_data["choices"]) > 0:
                    content = chat_data["choices"][0].get("message", {}).get("content", "")
                
                # Create response in Responses API format
                response_data = create_basic_response(request.model, content)
                
                # Add usage information if available
                if "usage" in chat_data:
                    response_data["usage"] = chat_data["usage"]
                
                # Log full request/response cycle for debugging
                log_request_response(request_id, {
                    "type": "responses_api",
                    "original_request": request.dict(),
                    "converted_request": chat_request,
                    "llm_response": chat_data,
                    "final_response": response_data
                })
                
                logger.info(f"[{request_id}] Request handling complete, returning response")
                return response_data
                
    except Exception as e:
        logger.error(f"[{request_id}] Error handling request: {str(e)}")
        logger.exception(f"[{request_id}] Full exception details:")
        raise HTTPException(status_code=500, detail=f"Error handling request: {str(e)}")
