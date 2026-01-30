"""vLLM client using OpenAI-compatible API."""

import os
from typing import Iterator, Optional

from openai import OpenAI
from pydantic import BaseModel


class Message(BaseModel):
    """A conversation message."""
    role: str  # "system", "user", "assistant", "tool"
    content: str
    name: Optional[str] = None
    tool_call_id: Optional[str] = None
    tool_calls: Optional[list] = None


class VLLMClient:
    """Client for vLLM OpenAI-compatible API with prefix-caching support."""
    
    def __init__(
        self,
        base_url: str = "http://localhost:8100/v1",
        model: str = "nvidia/NVIDIA-Nemotron-3-Nano-30B-A3B-FP8",
    ):
        self.client = OpenAI(base_url=base_url, api_key="not-needed")
        self.model = model
    
    def chat(
        self,
        messages: list[dict],
        tools: Optional[list[dict]] = None,
        stream: bool = True,
        temperature: float = 0.7,
        max_tokens: int = 2048,
    ) -> Iterator[str] | str:
        """
        Send messages to vLLM and get response.
        
        Prefix-caching works automatically when the same message prefix
        is sent across requests (e.g., system prompt + history).
        
        Args:
            messages: List of message dicts with role/content
            tools: Optional list of tool definitions (OpenAI format)
            stream: Whether to stream the response
            temperature: Sampling temperature
            max_tokens: Maximum tokens to generate
            
        Returns:
            If stream=True: Iterator yielding content chunks
            If stream=False: Complete response string
        """
        kwargs = {
            "model": self.model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
            "stream": stream,
        }
        
        if tools:
            kwargs["tools"] = tools
            kwargs["tool_choice"] = "auto"
        
        if stream:
            return self._stream_response(**kwargs)
        else:
            response = self.client.chat.completions.create(**kwargs)
            return response.choices[0].message.content or ""
    
    def _stream_response(self, **kwargs) -> Iterator[str]:
        """Stream response chunks."""
        response = self.client.chat.completions.create(**kwargs)
        for chunk in response:
            if chunk.choices and chunk.choices[0].delta.content:
                yield chunk.choices[0].delta.content
    
    def chat_with_tools(
        self,
        messages: list[dict],
        tools: list[dict],
        tool_executor: callable,
        max_tool_rounds: int = 5,
    ) -> tuple[str, list[dict]]:
        """
        Chat with tool calling support.
        
        Args:
            messages: Conversation messages
            tools: Tool definitions
            tool_executor: Function to execute tools (name, args) -> result
            max_tool_rounds: Maximum number of tool calling rounds
            
        Returns:
            Tuple of (final response, updated messages)
        """
        messages = list(messages)  # Copy to avoid mutation
        
        for _ in range(max_tool_rounds):
            response = self.client.chat.completions.create(
                model=self.model,
                messages=messages,
                tools=tools,
                tool_choice="auto",
            )
            
            assistant_message = response.choices[0].message
            
            # No tool calls - we have the final response
            if not assistant_message.tool_calls:
                return assistant_message.content or "", messages
            
            # Add assistant message with tool calls
            messages.append({
                "role": "assistant",
                "content": assistant_message.content or "",
                "tool_calls": [
                    {
                        "id": tc.id,
                        "type": "function",
                        "function": {
                            "name": tc.function.name,
                            "arguments": tc.function.arguments,
                        }
                    }
                    for tc in assistant_message.tool_calls
                ]
            })
            
            # Execute each tool and add results
            for tool_call in assistant_message.tool_calls:
                import json
                try:
                    args = json.loads(tool_call.function.arguments)
                    result = tool_executor(tool_call.function.name, args)
                except Exception as e:
                    result = f"Error: {e}"
                
                messages.append({
                    "role": "tool",
                    "tool_call_id": tool_call.id,
                    "content": str(result),
                })
        
        # Max rounds reached - get final response
        response = self.client.chat.completions.create(
            model=self.model,
            messages=messages,
        )
        return response.choices[0].message.content or "", messages


def create_client() -> VLLMClient:
    """Create client from environment variables."""
    from dotenv import load_dotenv
    load_dotenv()
    
    return VLLMClient(
        base_url=os.getenv("VLLM_URL", "http://localhost:8100/v1"),
        model=os.getenv("MODEL_ID", "nvidia/NVIDIA-Nemotron-3-Nano-30B-A3B-FP8"),
    )
