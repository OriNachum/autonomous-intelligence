"""
Handler for the Responses API endpoints.
"""
import json
import time
import httpx
import uuid
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
    create_basic_response,
    stream_generator
)
from config import OPENAI_BASE_URL_STRIPPED, REQUEST_TIMEOUT, logger

async def handle_responses(request: ResponseRequest, raw_request: Request):
    """
    Handle Responses API requests by converting to Chat Completions formSat
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

def generate_uuid():
    return str(uuid.uuid4())

async def stream_generator(response, model, request_id, store=False, temperature=0, top_p=0):
    """
    Generate a stream of SSE events from the API response.
    Support for both explicit function calls and function calls embedded in content.
    Also supports both traditional function_call and newer tool_calls formats.
    """
    # Track function call state
    function_call_active = False
    tool_calls_active = False
    function_name = None
    function_args_buffer = {}  # Track arguments by call ID
    active_tool_call_ids = []
    item_id = f"item-{generate_uuid()}"
    output_index = 0
    content_buffer = ""  # Buffer to accumulate content for potential JSON function call detection
    has_emitted_content_start = False
    
    try:
        async for line in response.aiter_lines():
            logger.info(f"[{request_id}] Streaming chunk: {line}")
            if line:
                if line.startswith('data: '):
                    data = line[6:]  # Skip 'data: ' prefix
                    
                    # Handle completion of stream
                    if data.strip() == '[DONE]':
                        # Check if we've accumulated content that looks like a function call
                        if content_buffer and not function_call_active and not tool_calls_active:
                            try:
                                # Try to parse content as JSON
                                json_content = json.loads(content_buffer)
                                
                                # If it has a name and parameters, it's likely a function call
                                if isinstance(json_content, dict) and "name" in json_content and "parameters" in json_content:
                                    function_name = json_content["name"]
                                    arguments = json.dumps(json_content["parameters"])
                                    
                                    # Emit function call events
                                    yield f'data: {json.dumps({"type": "response.function_call", "item_id": item_id, "output_index": output_index, "name": function_name})}\n\n'
                                    yield f'data: {json.dumps({"type": "response.function_call_arguments.delta", "item_id": item_id, "output_index": output_index, "delta": arguments})}\n\n'
                                    yield f'data: {json.dumps({"type": "response.function_call_arguments.done", "item_id": item_id, "output_index": output_index, "arguments": arguments})}\n\n'
                                    
                                    # We've handled this content as a function call, so don't emit it as content
                                    content_buffer = ""
                            except json.JSONDecodeError:
                                # Not a valid JSON, just ignore
                                pass
                        
                        # If we were in an explicit function call, send the final done event
                        if function_call_active:
                            yield f'data: {json.dumps({"type": "response.function_call_arguments.done", "item_id": item_id, "output_index": output_index, "arguments": function_args_buffer.get("default", "")})}\n\n'
                        
                        # Send done events for any active tool calls
                        if tool_calls_active:
                            for call_id in active_tool_call_ids:
                                if call_id in function_args_buffer:
                                    yield f'data: {json.dumps({"type": "response.function_call_arguments.done", "item_id": item_id, "output_index": output_index, "arguments": function_args_buffer[call_id]})}\n\n'
                        
                        # If no content or function call was emitted, ensure we emit at least an empty content block
                        if not has_emitted_content_start and not function_call_active and not tool_calls_active:
                            # Emit an empty content block to ensure the client gets something
                            yield f'data: {json.dumps({"type": "response.content_block_delta", "delta": "", "item_id": item_id, "output_index": output_index})}\n\n'
                        
                        yield f'data: [DONE]\n\n'
                        break
                    
                    try:
                        chunk = json.loads(data)
                        # Handle function call in the delta
                        if 'choices' in chunk and len(chunk['choices']) > 0:
                            choice = chunk['choices'][0]
                            
                            # Check for tool_calls finish_reason
                            if choice.get('finish_reason') == 'tool_calls':
                                logger.info(f"[{request_id}] Detected tool_calls finish_reason, sending done events")
                                # No additional processing needed at this point, done events sent at [DONE]

                            # Handle tool_calls (newer OpenAI format)
                            if 'delta' in choice and 'tool_calls' in choice['delta']:
                                tool_calls_active = True
                                
                                for tool_call in choice['delta']['tool_calls']:
                                    call_id = tool_call.get('id', 'unknown')
                                    if call_id not in active_tool_call_ids:
                                        active_tool_call_ids.append(call_id)
                                    
                                    # Check for function type tool calls
                                    if tool_call.get('type') == 'function' and 'function' in tool_call:
                                        # Emit function call event with name
                                        if 'name' in tool_call['function']:
                                            function_name = tool_call['function']['name']
                                            yield f'data: {json.dumps({"type": "response.function_call", "item_id": item_id, "output_index": output_index, "name": function_name})}\n\n'
                                        
                                        # Handle arguments 
                                        if 'arguments' in tool_call['function']:
                                            args_delta = tool_call['function']['arguments']
                                            
                                            # Initialize if not exist
                                            if call_id not in function_args_buffer:
                                                function_args_buffer[call_id] = ""
                                                
                                            function_args_buffer[call_id] += args_delta
                                            
                                            # Send the delta event
                                            yield f'data: {json.dumps({"type": "response.function_call_arguments.delta", "item_id": item_id, "output_index": output_index, "delta": args_delta})}\n\n'
                            
                            # Handle traditional function_call (older OpenAI format)
                            elif 'delta' in choice and 'function_call' in choice['delta']:
                                function_call_active = True
                                
                                # Capture the function name and emit the function call event
                                if 'name' in choice['delta']['function_call']:
                                    function_name = choice['delta']['function_call']['name']
                                    yield f'data: {json.dumps({"type": "response.function_call", "item_id": item_id, "output_index": output_index, "name": function_name})}\n\n'
                                
                                # Stream function arguments as they arrive
                                if 'arguments' in choice['delta']['function_call']:
                                    args_delta = choice['delta']['function_call']['arguments']
                                    
                                    # Store in the buffer under "default" key
                                    if "default" not in function_args_buffer:
                                        function_args_buffer["default"] = ""
                                    function_args_buffer["default"] += args_delta
                                    
                                    # Send the delta event
                                    yield f'data: {json.dumps({"type": "response.function_call_arguments.delta", "item_id": item_id, "output_index": output_index, "delta": args_delta})}\n\n'
                            
                            # Handle normal content delta - including empty content
                            elif 'delta' in choice and 'content' in choice['delta']:
                                content_delta = choice['delta']['content'] or ""
                                content_buffer += content_delta
                                has_emitted_content_start = True
                                
                                # Always emit as content initially
                                content_event = {
                                    "type": "response.content_block_delta",
                                    "delta": content_delta,
                                    "item_id": item_id,
                                    "output_index": output_index
                                }
                                yield f'data: {json.dumps(content_event)}\n\n'
                                
                            # Check for finish reason to see if we have a complete message
                            if choice.get('finish_reason') == 'stop':
                                if content_buffer:
                                    # Try to parse the full content buffer as JSON function call
                                    try:
                                        json_content = json.loads(content_buffer)
                                        
                                        # If it has a name and parameters, it's likely a function call
                                        if isinstance(json_content, dict) and "name" in json_content and "parameters" in json_content:
                                            function_name = json_content["name"]
                                            arguments = json.dumps(json_content["parameters"])
                                            
                                            # Emit function call events
                                            yield f'data: {json.dumps({"type": "response.function_call", "item_id": item_id, "output_index": output_index, "name": function_name})}\n\n'
                                            yield f'data: {json.dumps({"type": "response.function_call_arguments.delta", "item_id": item_id, "output_index": output_index, "delta": arguments})}\n\n'
                                            yield f'data: {json.dumps({"type": "response.function_call_arguments.done", "item_id": item_id, "output_index": output_index, "arguments": arguments})}\n\n'
                                    except json.JSONDecodeError:
                                        # Not a valid JSON, just continue
                                        pass
                                # If we get finish_reason=stop with empty content and no other events emitted, emit an empty content block
                                elif not has_emitted_content_start and not function_call_active and not tool_calls_active:
                                    has_emitted_content_start = True
                                    yield f'data: {json.dumps({"type": "response.content_block_delta", "delta": "", "item_id": item_id, "output_index": output_index})}\n\n'
                            
                    except json.JSONDecodeError:
                        logger.error(f"[{request_id}] Error parsing JSON chunk: {data}")
    
    except Exception as e:
        logger.error(f"[{request_id}] Error in stream_generator: {str(e)}")
        logger.exception(f"[{request_id}] Full exception details:")

def process_input_messages(input_list, request_id):
    """
    Process input messages to standardized format
    with improved function call output handling.
    """
    messages = []
    logger.info(f"[{request_id}] Raw input (list): {input_list}")
    
    for message in input_list:
        logger.info(f"[{request_id}] Processing message: {message}")
        
        # Handle regular user/assistant messages
        if isinstance(message, dict) and 'role' in message and 'content' in message:
            messages.append({
                'role': message['role'],
                'content': message['content']
            })
            logger.info(f"[{request_id}] Added regular message with role: {message['role']}")
        
        # Handle function call outputs
        elif isinstance(message, dict) and message.get('type') == 'function_call_output':
            output = message.get('output', '')
            # Ensure function_name always has a value
            function_name = message.get('function_name')
            if not function_name:
                function_name = 'unknown_function'
                logger.warning(f"[{request_id}] Function name missing, using default: {function_name}")
            
            # Package as a function call message
            logger.info(f"[{request_id}] Adding function output message for {function_name}: {output}")
            
            # Add function result to messages
            messages.append({
                'role': 'function',
                'name': function_name,
                'content': output
            })
            
            # Add a follow-up user message to prompt the model for a response to the function output
            messages.append({
                'role': 'user',
                'content': f"Please respond to the function output from {function_name}"
            })
            logger.info(f"[{request_id}] Added function output and follow-up prompt for {function_name}")
        
        # Handle content block messages (text content)
        elif isinstance(message, dict) and message.get('type') == 'content_block':
            content = message.get('content', '')
            role = message.get('role', 'user')
            messages.append({
                'role': role,
                'content': content
            })
            logger.info(f"[{request_id}] Added content block with role: {role}")
            
        # Handle image messages
        elif isinstance(message, dict) and message.get('type') == 'image':
            content = [{
                "type": "image_url",
                "image_url": {
                    "url": message.get('url', ''),
                    "detail": message.get('detail', 'auto')
                }
            }]
            
            # If there's text with the image, add it to content
            if message.get('text'):
                content.insert(0, {"type": "text", "text": message.get('text')})
                
            messages.append({
                'role': message.get('role', 'user'),
                'content': content
            })
            logger.info(f"[{request_id}] Added image message")
            
        # Handle tool/function calls
        elif isinstance(message, dict) and message.get('type') == 'function_call':
            # Function call being made (not the result)
            function_name = message.get('function_name', '')
            arguments = message.get('arguments', '{}')
            
            messages.append({
                'role': 'assistant',
                'content': None,
                'function_call': {
                    'name': function_name,
                    'arguments': arguments
                }
            })
            logger.info(f"[{request_id}] Added function call for {function_name}")
            
        # Handle system messages specifically
        elif isinstance(message, dict) and message.get('type') == 'system':
            messages.append({
                'role': 'system',
                'content': message.get('content', '')
            })
            logger.info(f"[{request_id}] Added system message")
            
        else:
            # Log unrecognized message format
            logger.warning(f"[{request_id}] Unrecognized message format, skipping: {message}")
    
    # If we somehow ended up with no messages, add a default message
    if not messages:
        logger.warning(f"[{request_id}] No messages were processed, adding a default user message")
        messages.append({
            'role': 'user',
            'content': 'Please provide a response for the given input.'
        })
    
    logger.info(f"[{request_id}] Converted messages format: {messages}")
    return messages