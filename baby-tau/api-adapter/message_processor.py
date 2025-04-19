"""
Message processing utilities for handling API input messages.
"""
import traceback
from config import logger

def process_input_messages(input_list, request_id):
    """
    Process input messages to standardized format
    with improved function call output handling.
    """
    messages = []
    logger.info(f"[{request_id}] Raw input (list): {input_list}")
    
    try:
        # Special case: look for standalone 'invalid arguments: undefined' in the first message
        if input_list and len(input_list) > 0:
            first_message = input_list[0]
            logger.info(f"[{request_id}] First message: {first_message}")
            
            # Check specifically for the invalid arguments error pattern
            if (isinstance(first_message, dict) and 
                first_message.get('output') == 'invalid arguments: undefined' and 
                first_message.get('type') == 'function_call_output'):
                
                logger.warning(f"[{request_id}] Found standalone invalid arguments error")
                error_message = {
                    'role': 'user',
                    'content': "The previous function call failed with error: invalid arguments: undefined. Please try again with valid arguments."
                }
                messages.append(error_message)
                logger.info(f"[{request_id}] Added error message for invalid arguments: {error_message}")
                # We have processed the error message, so we can return here
                logger.info(f"[{request_id}] Converted messages format: {messages}")
                return messages
    
        # Normal processing for all messages
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
                logger.info(f"[{request_id}] Processing function_call_output with output: {output}")
                
                # Ensure function_name always has a value
                function_name = message.get('function_name')
                if not function_name:
                    function_name = 'unknown_function'
                    logger.warning(f"[{request_id}] Function name missing, using default: {function_name}")
                else:
                    logger.info(f"[{request_id}] Function name: {function_name}")
                
                # Handle case where output is 'invalid arguments: undefined'
                if output and 'invalid arguments' in output:
                    logger.warning(f"[{request_id}] Detected invalid arguments in function output: {output}")
                    
                    # Add a more descriptive error message as function output
                    output = f"Error: {output}. The function call failed due to invalid arguments."
                    logger.info(f"[{request_id}] Enhanced error message: {output}")
                
                # Package as a function call message
                logger.info(f"[{request_id}] Adding function output message for {function_name}: {output}")
                
                # Add function result to messages
                function_message = {
                    'role': 'function',
                    'name': function_name,
                    'content': output
                }
                messages.append(function_message)
                logger.info(f"[{request_id}] Added function message: {function_message}")
                
                # Add a follow-up user message to prompt the model for a response to the function output
                follow_up_message = {
                    'role': 'user',
                    'content': f"Please respond to the function output from {function_name}. The previous function call failed with error: {output}"
                }
                messages.append(follow_up_message)
                logger.info(f"[{request_id}] Added follow-up prompt for {function_name}: {follow_up_message}")
            
            # Special handling for invalid arguments without function name (standalone error messages)
            elif isinstance(message, dict) and isinstance(message.get('output'), str) and 'invalid arguments' in message.get('output', ''):
                output = message.get('output', '')
                logger.warning(f"[{request_id}] Processing standalone invalid arguments error: {output}")
                
                # Create a user message explaining the error
                error_message = {
                    'role': 'user',
                    'content': f"The previous function call failed with error: {output}. Please try again with valid arguments."
                }
                messages.append(error_message)
                logger.info(f"[{request_id}] Added error message for invalid arguments: {error_message}")
                
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
                logger.info(f"[{request_id}] Processing image message")
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
                    logger.info(f"[{request_id}] Image has accompanying text: {message.get('text')}")
                    
                messages.append({
                    'role': message.get('role', 'user'),
                    'content': content
                })
                logger.info(f"[{request_id}] Added image message with URL: {message.get('url', '')}")
                
            # Handle tool/function calls
            elif isinstance(message, dict) and message.get('type') == 'function_call':
                # Function call being made (not the result)
                function_name = message.get('function_name', '')
                arguments = message.get('arguments', '{}')
                logger.info(f"[{request_id}] Processing function_call with name: {function_name} and arguments: {arguments}")
                
                function_call_message = {
                    'role': 'assistant',
                    'content': None,
                    'function_call': {
                        'name': function_name,
                        'arguments': arguments
                    }
                }
                messages.append(function_call_message)
                logger.info(f"[{request_id}] Added function call for {function_name}: {function_call_message}")
                
            # Handle system messages specifically
            elif isinstance(message, dict) and message.get('type') == 'system':
                system_message = {
                    'role': 'system',
                    'content': message.get('content', '')
                }
                messages.append(system_message)
                logger.info(f"[{request_id}] Added system message: {system_message}")
                
            else:
                # Log unrecognized message format
                logger.warning(f"[{request_id}] Unrecognized message format, skipping: {message}")
        
        # If we somehow ended up with no messages, add a default message
        if not messages:
            logger.warning(f"[{request_id}] No messages were processed, adding a default user message")
            default_message = {
                'role': 'user',
                'content': 'The previous function call failed with invalid arguments. Please try again with valid arguments.'
            }
            messages.append(default_message)
            logger.info(f"[{request_id}] Added default message: {default_message}")
    except Exception as e:
        logger.error(f"[{request_id}] Error processing messages: {e}")
        logger.error(f"[{request_id}] Exception traceback: {traceback.format_exc()}")
        # Ensure we return at least a basic message on error
        if not messages:
            error_handler_message = {
                'role': 'user',
                'content': 'An error occurred while processing the previous function call. Please try again.'
            }
            messages.append(error_handler_message)
            logger.info(f"[{request_id}] Added error handler message: {error_handler_message}")
    
    logger.info(f"[{request_id}] Converted messages format: {messages}")
    return messages
