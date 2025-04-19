"""
Utilities for converting between different API formats.
"""

import json
import uuid
from typing import Dict, Any, List, Union
from config import logger


def generate_uuid():
    return str(uuid.uuid4())

def process_input_messages(input_data: Union[List[Dict[str, Any]], str], request_id: str) -> List[Dict[str, Any]]:
    """
    Process input messages from the Responses API format to Chat Completions format
    """
    # Convert input format if it's a string
    if isinstance(input_data, str):
        logger.info(f"[{request_id}] Raw input (string): {input_data}")
        return [{"role": "user", "content": input_data}]
    else:
        logger.info(f"[{request_id}] Raw input (list): {json.dumps(input_data, default=str)}")
        
        # Process the input messages more carefully to ensure valid format
        messages = []
        for msg in input_data:
            logger.info(f"Processing message: {msg}")
            if isinstance(msg, dict):
                # Make sure message has both role and content
                if "role" in msg:
                    # Handle different content formats
                    content = ""
                    if "content" in msg:
                        # If content is a list (OpenAI Responses format)
                        if isinstance(msg["content"], list):
                            logger.info(f"Content is a list: {msg['content']}")
                            # Extract text from the list of content items
                            text_parts = []
                            for content_item in msg["content"]:
                                if isinstance(content_item, dict):
                                    # Handle known content types
                                    if content_item.get("type") == "input_text" or content_item.get("type") == "output_text":
                                        if "text" in content_item:
                                            text_parts.append(content_item["text"])
                                    elif "text" in content_item:
                                        text_parts.append(content_item["text"])
                            # Join all text parts
                            content = " ".join(text_parts)
                            logger.info(f"Extracted content: '{content}'")
                        # If content is a string
                        elif isinstance(msg["content"], str):
                            content = msg["content"]
                        # If content is something else
                        else:
                            logger.warning(f"Unexpected content type: {type(msg['content'])}, trying to convert to string")
                            try:
                                content = str(msg["content"])
                            except:
                                content = ""
                    
                    # Create properly formatted message
                    message = {
                        "role": msg["role"],
                        "content": content
                    }
                    
                    # Add name if it exists
                    if "name" in msg and msg["name"]:
                        message["name"] = msg["name"]
                        
                    messages.append(message)
        return messages

def convert_to_chat_request(messages: List[Dict[str, Any]], request, request_id: str) -> Dict[str, Any]:
    """
    Convert Responses API format to Chat Completions format
    """
    logger.info(f"[{request_id}] Converted messages format: {json.dumps(messages, default=str)}")
    
    chat_request = {
        "model": request.model,
        "messages": messages,
        "temperature": request.temperature,
        "top_p": request.top_p,
        "max_completion_tokens": request.max_output_tokens,
        "stream": request.stream,
        "store": request.store,
        "user": request.user,
        "metadata": request.metadata,
    }
    
    # Add tools if present
    if request.tools:
        chat_request["tools"] = request.tools
    
    if request.tool_choice:
        chat_request["tool_choice"] = request.tool_choice        
    
    # Add instructions as first system message if present
    if request.instructions:
        chat_request["messages"].insert(0, {
            "role": "system",
            "content": request.instructions
        })
    
    # Add reasoning effort if present
    if request.reasoning and request.reasoning.get("effort"):
        chat_request["reasoning_effort"] = request.reasoning.get("effort")
    
    # Filter out None values
    chat_request = {k: v for k, v in chat_request.items() if v is not None}
    
    logger.info(f"[{request_id}] Final chat request: {json.dumps(chat_request, default=str)}")
    return chat_request

def create_basic_response(model: str, content: str) -> Dict[str, Any]:
    """
    Create a basic response in Responses API format
    """
    response_id = f"resp_{uuid.uuid4().hex}"
    message_id = f"msg_{uuid.uuid4().hex}"
    
    return {
        "id": response_id,
        "object": "thread.message",
        "created_at": int(uuid.uuid1().time // 10**6),
        "thread_id": f"thread_{uuid.uuid4().hex}",
        "model": model,
        "role": "assistant",
        "content": [
            {
                "type": "output_text",
                "text": content,
                "annotations": []
            }
        ],
        "output_text": content,
        "metadata": {}
    }
