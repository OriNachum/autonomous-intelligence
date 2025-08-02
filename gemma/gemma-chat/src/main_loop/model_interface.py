"""Model interface for Gemma 3n multimodal model via OpenAI API"""

import logging
import asyncio
from typing import Dict, Any, List, Optional, Tuple
import time
import base64
import io
import json
from PIL import Image
import aiohttp

from ..config import Config

class ModelInterface:
    """Interface for Gemma 3n multimodal model"""
    
    def __init__(self, config: Config):
        self.config = config
        self.logger = logging.getLogger(__name__)
        
        # API configuration
        self.api_url = getattr(config, 'API_URL', 'http://localhost:8000')
        self.model_name = "gemma3n"
        self.max_history = getattr(config, 'MAX_HISTORY', 10)
        self.max_new_tokens = getattr(config, 'MAX_NEW_TOKENS', 100)
        self.temperature = getattr(config, 'TEMPERATURE', 0.7)
        
        # HTTP session for API calls
        self.session = None
        
        # Conversation history
        self.conversation_history: List[Dict[str, Any]] = []
        self.system_prompt = self._get_system_prompt()
        
        # Performance tracking
        self.inference_count = 0
        self.total_inference_time = 0
        self.last_inference_time = 0
        
        # API health status
        self.api_healthy = False
    
    async def _initialize_session(self):
        """Initialize HTTP session and check API health"""
        if self.session is None:
            self.session = aiohttp.ClientSession()
        
        try:
            async with self.session.get(f"{self.api_url}/health", timeout=5) as response:
                if response.status == 200:
                    self.api_healthy = True
                    self.logger.info(f"Connected to API at {self.api_url}")
                else:
                    self.api_healthy = False
                    self.logger.warning(f"API health check failed: {response.status}")
        except Exception as e:
            self.api_healthy = False
            self.logger.error(f"Failed to connect to API: {e}")
    
    async def _ensure_session(self):
        """Ensure HTTP session is initialized"""
        if self.session is None or not self.api_healthy:
            await self._initialize_session()
    
    def _get_system_prompt(self) -> str:
        """Get system prompt for Gemma"""
        return """You are Gemma, a helpful multimodal AI assistant. You can see through a camera, hear through a microphone, and communicate through text and speech.

Key behaviors:
- Only content in quotation marks will be spoken aloud
- Actions can be described with asterisks (*looking at the user*)
- You have access to real-time camera and audio input
- Respond naturally and conversationally
- Keep responses concise but helpful
- Target 400ms response time for first spoken word

Current capabilities:
- Camera: Object detection (humans, animals)
- Audio: Voice activity detection and wake word recognition
- Text: Terminal input processing
- Memory: Fact distillation and retrieval
"""
    
    async def process_multimodal_input(self, 
                                     text_input: Optional[str] = None,
                                     image_data: Optional[bytes] = None,
                                     audio_data: Optional[bytes] = None,
                                     context: Optional[Dict[str, Any]] = None) -> str:
        """Process multimodal input and generate response"""
        start_time = time.time()
        
        try:
            # Prepare input
            input_data = self._prepare_input(text_input, image_data, audio_data, context)
            
            # Generate response
            response = await self._generate_response(input_data)
            
            # Update conversation history
            self._update_conversation_history(input_data, response)
            
            # Track performance
            inference_time = time.time() - start_time
            self.inference_count += 1
            self.total_inference_time += inference_time
            self.last_inference_time = inference_time
            
            self.logger.debug(f"Generated response in {inference_time:.2f}s")
            
            return response
            
        except Exception as e:
            self.logger.error(f"Error in multimodal processing: {e}")
            return "I apologize, but I encountered an error processing your request."
    
    def _prepare_input(self, text_input: Optional[str], image_data: Optional[bytes], 
                      audio_data: Optional[bytes], context: Optional[Dict[str, Any]]) -> Dict[str, Any]:
        """Prepare multimodal input for the model"""
        input_data = {
            'text': text_input or "",
            'image': None,
            'audio': None,
            'context': context or {},
            'timestamp': time.time()
        }
        
        # Process image data
        if image_data:
            try:
                image = Image.open(io.BytesIO(image_data))
                input_data['image'] = image
                input_data['image_description'] = self._describe_image(image)
            except Exception as e:
                self.logger.error(f"Error processing image: {e}")
        
        # Process audio data
        if audio_data:
            input_data['audio'] = audio_data
            input_data['audio_description'] = "Audio input received"
        
        return input_data
    
    def _describe_image(self, image: Image.Image) -> str:
        """Basic image description (placeholder)"""
        # In a real implementation, this would use vision capabilities
        return f"Image of size {image.size[0]}x{image.size[1]}"
    
    async def _generate_response(self, input_data: Dict[str, Any]) -> str:
        """Generate response from input data using OpenAI API"""
        await self._ensure_session()
        
        if not self.api_healthy:
            return self._mock_response(input_data)
        
        try:
            # Build messages for OpenAI API format
            messages = self._build_openai_messages(input_data)
            
            # Prepare API request
            payload = {
                "model": self.model_name,
                "messages": messages,
                "max_new_tokens": self.max_new_tokens,
                "temperature": self.temperature,
                "stream": False
            }
            
            # Make API request
            async with self.session.post(
                f"{self.api_url}/v1/chat/completions",
                json=payload,
                timeout=30
            ) as response:
                if response.status == 200:
                    result = await response.json()
                    if 'choices' in result and len(result['choices']) > 0:
                        content = result['choices'][0]['message']['content']
                        return content.strip()
                    else:
                        self.logger.warning("No choices in API response")
                        return "I apologize, but I didn't receive a proper response."
                else:
                    error_text = await response.text()
                    self.logger.error(f"API request failed: {response.status} - {error_text}")
                    return "I apologize, but I'm having trouble connecting to the model right now."
            
        except asyncio.TimeoutError:
            self.logger.error("API request timed out")
            return "I apologize, but the response is taking too long. Please try again."
        except Exception as e:
            self.logger.error(f"Error calling API: {e}")
            return "I apologize, but I encountered an error processing your request."
    
    def _mock_response(self, input_data: Dict[str, Any]) -> str:
        """Mock response for testing"""
        text = input_data.get('text', '')
        has_image = input_data.get('image') is not None
        has_audio = input_data.get('audio') is not None
        
        responses = [
            f"\"I heard you say: {text}\"",
            f"\"I understand your message about {text}\"",
            "\"That's interesting. Tell me more.\"",
            "\"I see what you mean.\"",
            "\"How can I help you with that?\""
        ]
        
        if has_image:
            responses.extend([
                "\"I can see the image you've shared.\"",
                "\"Looking at the image, I notice several interesting details.\"",
                "*examining the image carefully*"
            ])
        
        if has_audio:
            responses.extend([
                "\"I heard your voice input.\"",
                "\"Your audio came through clearly.\""
            ])
        
        import random
        return random.choice(responses)
    
    def _build_openai_messages(self, input_data: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Build messages array for OpenAI API format"""
        messages = []
        
        # Add system message with context
        system_content = self._build_system_content(input_data)
        messages.append({"role": "system", "content": system_content})
        
        # Add recent conversation history
        for msg in self.conversation_history[-5:]:  # Last 5 messages
            if msg['type'] == 'user':
                messages.append({"role": "user", "content": msg['content']})
            elif msg['type'] == 'assistant':
                messages.append({"role": "assistant", "content": msg['content']})
        
        # Add current user input
        user_content = self._build_user_content(input_data)
        if user_content:
            messages.append({"role": "user", "content": user_content})
        
        return messages
    
    def _build_system_content(self, input_data: Dict[str, Any]) -> str:
        """Build system message content with context"""
        content_parts = [self.system_prompt]
        
        # Add memory context if available
        context = input_data.get('context', {})
        if context.get('relevant_facts'):
            content_parts.append("\nRelevant facts from memory:")
            for fact in context['relevant_facts'][:5]:  # Top 5 relevant facts
                content_parts.append(f"- {fact}")
        
        if context.get('important_facts'):
            content_parts.append("\nImportant facts to remember:")
            for fact in context['important_facts']:
                content_parts.append(f"- {fact}")
        
        if context.get('long_term_facts'):
            content_parts.append("\nRelevant long-term memories:")
            for fact in context['long_term_facts']:
                content_parts.append(f"- {fact}")
        
        # Add current multimodal input context
        if context.get('wake_word_active'):
            content_parts.append(f"\nNote: User activated with wake word '{context.get('wake_word', 'unknown')}'")
        
        if context.get('detections'):
            detected_objects = [d.get('class_name') for d in context['detections']]
            if detected_objects:
                content_parts.append(f"Currently visible: {', '.join(detected_objects)}")
        
        return "\n".join(content_parts)
    
    def _build_user_content(self, input_data: Dict[str, Any]) -> Optional[List[Dict[str, Any]]]:
        """Build user message content for multimodal input"""
        content = []
        
        # Add text content
        if input_data.get('text'):
            content.append({"type": "text", "text": input_data['text']})
        
        # Add image content if available
        if input_data.get('image'):
            try:
                # Convert PIL Image to base64
                buffered = io.BytesIO()
                input_data['image'].save(buffered, format="JPEG")
                img_str = base64.b64encode(buffered.getvalue()).decode()
                
                content.append({
                    "type": "image_url",
                    "image_url": {"url": f"data:image/jpeg;base64,{img_str}"}
                })
            except Exception as e:
                self.logger.error(f"Error encoding image: {e}")
                content.append({"type": "text", "text": "[Image could not be processed]"})
        
        # Add audio description if available
        if input_data.get('audio_description'):
            content.append({"type": "text", "text": f"[Audio: {input_data['audio_description']}]"})
        
        return content if content else None
    
    def _update_conversation_history(self, input_data: Dict[str, Any], response: str):
        """Update conversation history"""
        # Add user input
        user_content = []
        if input_data.get('text'):
            user_content.append(input_data['text'])
        if input_data.get('image'):
            user_content.append("[IMAGE]")
        if input_data.get('audio'):
            user_content.append("[AUDIO]")
        
        if user_content:
            self.conversation_history.append({
                'type': 'user',
                'content': ' | '.join(user_content),
                'timestamp': input_data['timestamp']
            })
        
        # Add assistant response
        self.conversation_history.append({
            'type': 'assistant',
            'content': response,
            'timestamp': time.time()
        })
        
        # Trim history
        if len(self.conversation_history) > self.max_history * 2:
            self.conversation_history = self.conversation_history[-self.max_history * 2:]
    
    def get_conversation_history(self) -> List[Dict[str, Any]]:
        """Get conversation history"""
        return self.conversation_history.copy()
    
    def clear_conversation_history(self):
        """Clear conversation history"""
        self.conversation_history = []
        self.logger.info("Conversation history cleared")
    
    def get_statistics(self) -> Dict[str, Any]:
        """Get model interface statistics"""
        avg_inference_time = (self.total_inference_time / self.inference_count 
                             if self.inference_count > 0 else 0)
        
        return {
            'model_name': self.model_name,
            'api_url': self.api_url,
            'api_healthy': self.api_healthy,
            'inference_count': self.inference_count,
            'total_inference_time': self.total_inference_time,
            'avg_inference_time': avg_inference_time,
            'last_inference_time': self.last_inference_time,
            'conversation_length': len(self.conversation_history),
            'max_history': self.max_history,
            'max_new_tokens': self.max_new_tokens,
            'temperature': self.temperature
        }
    
    async def cleanup(self):
        """Cleanup resources"""
        if self.session:
            await self.session.close()
            self.session = None