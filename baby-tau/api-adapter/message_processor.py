"""
Message processing utilities for handling API input messages.
"""
from config import logger

def process_input_messages(input_list, request_id):
    """
    Process input messages to standardized format
    with improved function call output handling.
    """
    messages = []
    logger.info(f"[{request_id}] Raw input (list): {input_list}")
    
    for message in input_list:
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
