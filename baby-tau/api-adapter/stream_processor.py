"""
Stream processing utilities for handling API response streams.
"""
import json
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
                                tool_calls_complete = True
                                
                                # Send done events for all active tool calls immediately
                                for call_id in active_tool_call_ids:
                                    if call_id in function_args_buffer:
                                        yield f'data: {json.dumps({"type": "response.function_call_arguments.done", "item_id": item_id, "output_index": output_index, "arguments": function_args_buffer[call_id]})}\n\n'

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
                                            
                                            # If this is the last chunk based on our tool_calls_complete flag, 
                                            # also send the done event immediately
                                            if tool_calls_complete:
                                                yield f'data: {json.dumps({"type": "response.function_call_arguments.done", "item_id": item_id, "output_index": output_index, "arguments": function_args_buffer[call_id]})}\n\n'
                            
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
                            if choice.get('finish_reason') == 'stop' or choice.get('finish_reason') == 'tool_calls':
                                if content_buffer and choice.get('finish_reason') == 'stop':
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
                                # Make sure tool_calls finish_reason emits done events for all active tool calls
                                elif choice.get('finish_reason') == 'tool_calls':
                                    logger.info(f"[{request_id}] Got tool_calls finish_reason, emitting done events for all active tool calls")
                                    # Send done events for any active tool call that doesn't have a done event yet
                                    for call_id in active_tool_call_ids:
                                        if call_id in function_args_buffer:
                                            yield f'data: {json.dumps({"type": "response.function_call_arguments.done", "item_id": item_id, "output_index": output_index, "arguments": function_args_buffer[call_id]})}\n\n'
                                # If we get finish_reason=stop with empty content and no other events emitted, emit an empty content block
                                elif not has_emitted_content_start and not function_call_active and not tool_calls_active:
                                    has_emitted_content_start = True
                                    yield f'data: {json.dumps({"type": "response.content_block_delta", "delta": "", "item_id": item_id, "output_index": output_index})}\n\n'
                            
                    except json.JSONDecodeError:
                        logger.error(f"[{request_id}] Error parsing JSON chunk: {data}")
                        # If we get an invalid JSON in the stream, try to pass it through as raw SSE
                        if data.strip() != '[DONE]':  # Avoid duplicating [DONE] events
                            yield f'data: {data}\n\n'
    
    except Exception as e:
        logger.error(f"[{request_id}] Error in stream_generator: {str(e)}")
        logger.exception(f"[{request_id}] Full exception details:")
