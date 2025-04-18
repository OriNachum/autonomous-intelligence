"""
Utilities for handling streaming responses.
"""

import json
import time
import uuid
from typing import Dict, Any, AsyncGenerator
import httpx
from config import logger

async def stream_generator(response: httpx.Response, request_model: str, request_id: str, 
                           store: bool, temperature: float, top_p: float) -> AsyncGenerator[str, None]:
    """
    Generate a stream of Server-Sent Events from a streaming response
    """
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
            "model": request_model,
            "output": [],
            "parallel_tool_calls": True,
            "previous_response_id": None,
            "reasoning": {
                "effort": None,
                "summary": None
            },
            "store": store,
            "temperature": temperature,
            "text": {
                "format": {
                    "type": "text"
                }
            },
            "tool_choice": "auto",
            "tools": [],
            "top_p": top_p,
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
        "response": response_created["response"]
    }
    
    yield f"data: {json.dumps(response_in_progress)}\n\n"
    
    # Process each line from the streaming response
    async for line in response.aiter_lines():
        # Log chunk for debugging
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
                            "model": request_model,
                            "output": output_items,
                            "previous_response_id": None,
                            "reasoning_effort": None,
                            "store": store,
                            "temperature": temperature,
                            "text": {
                                "format": {
                                    "type": "text"
                                }
                            },
                            "tool_choice": "auto",
                            "tools": [],
                            "top_p": top_p,
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
