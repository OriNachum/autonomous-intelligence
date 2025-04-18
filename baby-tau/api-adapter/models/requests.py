"""
Pydantic models for API requests.
"""

from typing import List, Dict, Any, Optional, Union
from pydantic import BaseModel, Field
import uuid

class ResponseContent(BaseModel):
    type: str = "output_text"
    text: str
    annotations: List[Any] = Field(default_factory=list)

class ResponseMessage(BaseModel):
    id: str = Field(default_factory=lambda: f"msg_{uuid.uuid4().hex}")
    type: str = "message"
    role: str
    content: List[ResponseContent]

class ResponseRequest(BaseModel):
    model: str
    input: Union[List[Dict[str, Any]], str]
    temperature: Optional[float] = None
    top_p: Optional[float] = None
    max_output_tokens: Optional[int] = None
    status: Optional[str] = None
    error: Optional[str] = None
    incomplete_details: Optional[str] = None
    stream: Optional[bool] = False
    previous_response_id: Optional[str] = None
    store: Optional[bool] = True
    instructions: Optional[str] = None
    reasoning: Optional[Dict[str, Any]] = None
    parallel_tool_calls: Optional[bool] = True
    tool_choice: Optional[str] = None
    tools: Optional[List[Dict[str, Any]]] = None
    truncation: Optional[str] = None
    user: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None
