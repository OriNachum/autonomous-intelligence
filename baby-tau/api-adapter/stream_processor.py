"""
Stream processing utilities for handling API response streams.
"""
import json
import traceback
from utils import generate_uuid
from config import logger

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
    tool_calls_complete = False  # Track when tool_calls have been marked as complete
    
    logger.info(f"[{request_id}] === STREAM PROCESSOR STARTED ===")
    logger.info(f"[{request_id}] Processing stream for model: {model}")
    
    try:
        async for line in response.aiter_lines():
            logger.info(f"[{request_id}] Streaming chunk raw: {line}")
            if line:
                if line.startswith('data: '):
                    data = line[6:]  # Skip 'data: ' prefix
                    
                    # Handle completion of stream
                    if data.strip() == '[DONE]':
                        logger.info(f"[{request_id}] Got [DONE] event, function_call_active={function_call_active}, tool_calls_active={tool_calls_active}")
                        logger.info(f"[{request_id}] Content buffer: {content_buffer}")
                        
                        # Check if we've accumulated content that looks like a function call
                        if content_buffer and not function_call_active and not tool_calls_active:
                            logger.info(f"[{request_id}] Checking content buffer for function call: {content_buffer}")
                            try:
                                # Try to parse content as JSON
                                json_content = json.loads(content_buffer)
                                logger.info(f"[{request_id}] Successfully parsed content as JSON: {json_content}")
                                
                                # If it has a name and parameters, it's likely a function call
                                if isinstance(json_content, dict) and "name" in json_content and "parameters" in json_content:
                                    function_name = json_content["name"]
                                    arguments = json.dumps(json_content["parameters"])
                                    
                                    logger.info(f"[{request_id}] Content appears to be a function call: {function_name} with args: {arguments}")
                                    
                                    # Emit function call events
                                    yield f'data: {json.dumps({"type": "response.function_call", "item_id": item_id, "output_index": output_index, "name": function_name})}\n\n'
                                    yield f'data: {json.dumps({"type": "response.function_call_arguments.delta", "item_id": item_id, "output_index": output_index, "delta": arguments})}\n\n'
                                    yield f'data: {json.dumps({"type": "response.function_call_arguments.done", "item_id": item_id, "output_index": output_index, "arguments": arguments})}\n\n'
                                    
                                    # We've handled this content as a function call, so don't emit it as content
                                    content_buffer = ""
                                else:
                                    logger.info(f"[{request_id}] JSON doesn't have name and parameters structure: {json_content}")
                            except json.JSONDecodeError as e:
                                logger.info(f"[{request_id}] Content buffer is not valid JSON: {e}")
                                # Not a valid JSON, just ignore
                                pass
                        
                        # If we were in an explicit function call, send the final done event
                        if function_call_active:
                            logger.info(f"[{request_id}] Emitting final done event for function_call with args: {function_args_buffer.get('default', '')}")
                            yield f'data: {json.dumps({"type": "response.function_call_arguments.done", "item_id": item_id, "output_index": output_index, "arguments": function_args_buffer.get("default", "")})}\n\n'
                        
                        # Send done events for any active tool calls
                        if tool_calls_active:
                            logger.info(f"[{request_id}] Processing active tool calls: {active_tool_call_ids}")
                            for call_id in active_tool_call_ids:
                                if call_id in function_args_buffer:
                                    logger.info(f"[{request_id}] Emitting done event for tool call {call_id} with args: {function_args_buffer[call_id]}")
                                    yield f'data: {json.dumps({"type": "response.function_call_arguments.done", "item_id": item_id, "output_index": output_index, "arguments": function_args_buffer[call_id]})}\n\n'
                                else:
                                    logger.warning(f"[{request_id}] Tool call ID {call_id} not found in args buffer")
                        
                        # If no content or function call was emitted, ensure we emit at least an empty content block
                        if not has_emitted_content_start and not function_call_active and not tool_calls_active:
                            # Emit an empty content block to ensure the client gets something
                            logger.info(f"[{request_id}] No content was emitted, sending empty content block")
                            yield f'data: {json.dumps({"type": "response.content_block_delta", "delta": "", "item_id": item_id, "output_index": output_index})}\n\n'
                        
                        yield f'data: [DONE]\n\n'
                        break
                    
                    try:
                        chunk = json.loads(data)
                        logger.info(f"[{request_id}] Parsed JSON chunk: {json.dumps(chunk)}")
                        
                        # Handle function call in the delta
                        if 'choices' in chunk and len(chunk['choices']) > 0:
                            choice = chunk['choices'][0]
                            logger.info(f"[{request_id}] Processing choice: {json.dumps(choice)}")
                            
                            # Check for tool_calls finish_reason
                            if choice.get('finish_reason') == 'tool_calls':
                                logger.info(f"[{request_id}] Detected tool_calls finish_reason, sending done events")
                                tool_calls_complete = True
                                
                                # Send done events for all active tool calls immediately
                                for call_id in active_tool_call_ids:
                                    if call_id in function_args_buffer:
                                        logger.info(f"[{request_id}] Emitting done event for tool call {call_id} on finish_reason")
                                        yield f'data: {json.dumps({"type": "response.function_call_arguments.done", "item_id": call_id, "output_index": output_index, "arguments": function_args_buffer[call_id]})}\n\n'
                                    else:
                                        logger.warning(f"[{request_id}] Tool call ID {call_id} not found in args buffer on finish_reason")

                            # Handle tool_calls (newer OpenAI format)
                            if 'delta' in choice and 'tool_calls' in choice['delta']:
                                logger.info(f"[{request_id}] Found tool_calls in delta")
                                tool_calls = choice['delta']['tool_calls']
                                logger.info(f"[{request_id}] Processing tool_calls: {json.dumps(tool_calls)}")
                                tool_calls_active = True
                                
                                for tool_call in tool_calls:
                                    call_id = tool_call.get('id', f"call_{generate_uuid()}")
                                    if call_id not in active_tool_call_ids:
                                        active_tool_call_ids.append(call_id)
                                        logger.info(f"[{request_id}] Added new tool call ID: {call_id}")
                                    
                                    # Check for function type tool calls
                                    if tool_call.get('type') == 'function' and 'function' in tool_call:
                                        # Emit function call event with name
                                        if 'name' in tool_call['function']:
                                            function_name = tool_call['function']['name']
                                            logger.info(f"[{request_id}] Found function name in tool_call: {function_name}")
                                            yield f'data: {json.dumps({"type": "response.function_call", "item_id": call_id, "output_index": output_index, "name": function_name})}\n\n'
                                        
                                        # Handle arguments 
                                        if 'arguments' in tool_call['function']:
                                            args_delta = tool_call['function']['arguments']
                                            logger.info(f"[{request_id}] Found function arguments in tool_call: {args_delta}")
                                            
                                            # Initialize if not exist
                                            if call_id not in function_args_buffer:
                                                function_args_buffer[call_id] = ""
                                                logger.info(f"[{request_id}] Initialized args buffer for tool call {call_id}")
                                                
                                            function_args_buffer[call_id] += args_delta
                                            logger.info(f"[{request_id}] Updated args buffer for {call_id}: {function_args_buffer[call_id]}")
                                            
                                            # Send the delta event
                                            logger.info(f"[{request_id}] Emitting delta event for tool call {call_id}")
                                            yield f'data: {json.dumps({"type": "response.function_call_arguments.delta", "item_id": call_id, "output_index": output_index, "delta": args_delta})}\n\n'
                                            
                                            # If this is the last chunk based on our tool_calls_complete flag, 
                                            # also send the done event immediately
                                            if tool_calls_complete:
                                                logger.info(f"[{request_id}] Tool calls complete, emitting done event for {call_id}")
                                                yield f'data: {json.dumps({"type": "response.function_call_arguments.done", "item_id": call_id, "output_index": output_index, "arguments": function_args_buffer[call_id]})}\n\n'
                            
                            # Handle traditional function_call (older OpenAI format)
                            elif 'delta' in choice and 'function_call' in choice['delta']:
                                function_call_active = True
                                logger.info(f"[{request_id}] Processing function_call in delta: {choice['delta']['function_call']}")
                                
                                # Capture the function name and emit the function call event
                                if 'name' in choice['delta']['function_call']:
                                    function_name = choice['delta']['function_call']['name']
                                    logger.info(f"[{request_id}] Found function name: {function_name}")
                                    yield f'data: {json.dumps({"type": "response.function_call", "item_id": item_id, "output_index": output_index, "name": function_name})}\n\n'
                                
                                # Stream function arguments as they arrive
                                if 'arguments' in choice['delta']['function_call']:
                                    args_delta = choice['delta']['function_call']['arguments']
                                    logger.info(f"[{request_id}] Found function arguments: {args_delta}")
                                    
                                    # Store in the buffer under "default" key
                                    if "default" not in function_args_buffer:
                                        function_args_buffer["default"] = ""
                                        logger.info(f"[{request_id}] Initialized default args buffer")
                                    function_args_buffer["default"] += args_delta
                                    logger.info(f"[{request_id}] Updated default args buffer: {function_args_buffer['default']}")
                                    
                                    # Send the delta event
                                    logger.info(f"[{request_id}] Emitting delta event for function_call")
                                    yield f'data: {json.dumps({"type": "response.function_call_arguments.delta", "item_id": item_id, "output_index": output_index, "delta": args_delta})}\n\n'
                            
                            # Handle normal content delta - including empty content
                            elif 'delta' in choice and 'content' in choice['delta']:
                                content_delta = choice['delta']['content'] or ""
                                content_buffer += content_delta
                                logger.info(f"[{request_id}] Content delta: '{content_delta}', updated content buffer: '{content_buffer}'")
                                has_emitted_content_start = True
                                
                                # Check if content looks like a function call JSON string (for Ollama and similar backends)
                                # This handles the case where the model returns a function call as a string rather than
                                # using the function_call or tool_calls format
                                if content_delta.startswith('{"name":') or content_buffer.startswith('{"name":'):
                                    logger.info(f"[{request_id}] Content appears to be a function call (starts with '{{\"name\":')")
                                    try:
                                        # Try to parse the content as a function call
                                        json_content = json.loads(content_buffer)
                                        logger.info(f"[{request_id}] Successfully parsed potential function call: {json_content}")
                                        
                                        # If it has a name and parameters, treat it as a function call
                                        if isinstance(json_content, dict) and "name" in json_content and ("parameters" in json_content or "arguments" in json_content):
                                            function_name = json_content["name"]
                                            # Handle different parameter field names
                                            arguments = json_content.get("parameters", json_content.get("arguments", "{}"))
                                            if not isinstance(arguments, str):
                                                arguments = json.dumps(arguments)
                                            
                                            # This is a function call, don't emit as content
                                            function_call_active = True
                                            
                                            # Emit function call events
                                            logger.info(f"[{request_id}] Detected function call in content: {function_name} with args: {arguments}")
                                            yield f'data: {json.dumps({"type": "response.function_call", "item_id": item_id, "output_index": output_index, "name": function_name})}\n\n'
                                            yield f'data: {json.dumps({"type": "response.function_call_arguments.delta", "item_id": item_id, "output_index": output_index, "delta": arguments})}\n\n'
                                            yield f'data: {json.dumps({"type": "response.function_call_arguments.done", "item_id": item_id, "output_index": output_index, "arguments": arguments})}\n\n'
                                            
                                            # Skip emitting as content
                                            continue
                                        else:
                                            logger.info(f"[{request_id}] Content has JSON format but doesn't match function call pattern")
                                    except json.JSONDecodeError as e:
                                        logger.info(f"[{request_id}] Content not parsable as JSON yet: {e}")
                                        # Not a complete JSON yet, or not actually JSON - emit as content
                                        pass
                                
                                # Always emit as content if we didn't detect a function call
                                content_event = {
                                    "type": "response.content_block_delta",
                                    "delta": content_delta,
                                    "item_id": item_id,
                                    "output_index": output_index
                                }
                                logger.info(f"[{request_id}] Emitting content block delta")
                                yield f'data: {json.dumps(content_event)}\n\n'
                                
                            # Check for finish reason to see if we have a complete message
                            if choice.get('finish_reason') == 'stop' or choice.get('finish_reason') == 'tool_calls':
                                logger.info(f"[{request_id}] Got finish_reason: {choice.get('finish_reason')}")
                                if content_buffer and choice.get('finish_reason') == 'stop':
                                    logger.info(f"[{request_id}] Checking content buffer for function call on finish: {content_buffer}")
                                    # Try to parse the full content buffer as JSON function call
                                    try:
                                        json_content = json.loads(content_buffer)
                                        logger.info(f"[{request_id}] Parsed content buffer as JSON: {json_content}")
                                        
                                        # If it has a name and parameters, it's likely a function call
                                        if isinstance(json_content, dict) and "name" in json_content and "parameters" in json_content:
                                            function_name = json_content["name"]
                                            arguments = json.dumps(json_content["parameters"])
                                            logger.info(f"[{request_id}] Detected function call on finish: {function_name} with args: {arguments}")
                                            
                                            # Emit function call events
                                            yield f'data: {json.dumps({"type": "response.function_call", "item_id": item_id, "output_index": output_index, "name": function_name})}\n\n'
                                            yield f'data: {json.dumps({"type": "response.function_call_arguments.delta", "item_id": item_id, "output_index": output_index, "delta": arguments})}\n\n'
                                            yield f'data: {json.dumps({"type": "response.function_call_arguments.done", "item_id": item_id, "output_index": output_index, "arguments": arguments})}\n\n'
                                        else:
                                            logger.info(f"[{request_id}] Content is JSON but not a function call: {json_content}")
                                    except json.JSONDecodeError as e:
                                        logger.info(f"[{request_id}] Content buffer is not valid JSON on finish: {e}")
                                        # Not a valid JSON, just continue
                                        pass
                                # Make sure tool_calls finish_reason emits done events for all active tool calls
                                elif choice.get('finish_reason') == 'tool_calls':
                                    logger.info(f"[{request_id}] Got tool_calls finish_reason, emitting done events for all active tool calls: {active_tool_call_ids}")
                                    # Send done events for any active tool call that doesn't have a done event yet
                                    for call_id in active_tool_call_ids:
                                        if call_id in function_args_buffer:
                                            logger.info(f"[{request_id}] Emitting done event for tool call {call_id} on finish_reason=tool_calls")
                                            yield f'data: {json.dumps({"type": "response.function_call_arguments.done", "item_id": call_id, "output_index": output_index, "arguments": function_args_buffer[call_id]})}\n\n'
                                        else:
                                            logger.warning(f"[{request_id}] Tool call ID {call_id} not found in args buffer")
                                # If we get finish_reason=stop with empty content and no other events emitted, emit an empty content block
                                elif not has_emitted_content_start and not function_call_active and not tool_calls_active:
                                    logger.info(f"[{request_id}] No content emitted yet, sending empty content block on finish")
                                    has_emitted_content_start = True
                                    yield f'data: {json.dumps({"type": "response.content_block_delta", "delta": "", "item_id": item_id, "output_index": output_index})}\n\n'
                            
                    except json.JSONDecodeError as e:
                        logger.error(f"[{request_id}] Error parsing JSON chunk: {data}. Error: {e}")
                        # If we get an invalid JSON in the stream, try to pass it through as raw SSE
                        if data.strip() != '[DONE]':  # Avoid duplicating [DONE] events
                            logger.info(f"[{request_id}] Passing through raw SSE: {data}")
                            yield f'data: {data}\n\n'
    
    except Exception as e:
        logger.error(f"[{request_id}] Error in stream_generator: {str(e)}")
        logger.error(f"[{request_id}] Exception traceback: {traceback.format_exc()}")
        
    logger.info(f"[{request_id}] === STREAM PROCESSOR FINISHED ===")
