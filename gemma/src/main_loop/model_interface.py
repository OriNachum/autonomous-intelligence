"""Model interface for Gemma 3n multimodal model"""

import logging
import asyncio
from typing import Dict, Any, List, Optional, Tuple
import numpy as np
import time
import base64
import io
from PIL import Image

try:
    import torch
    from transformers import pipeline, AutoTokenizer, AutoModelForCausalLM
    TRANSFORMERS_AVAILABLE = True
except ImportError:
    TRANSFORMERS_AVAILABLE = False
    logging.warning("Transformers not available, using mock model")

from ..config import Config

class ModelInterface:
    """Interface for Gemma 3n multimodal model"""
    
    def __init__(self, config: Config):
        self.config = config
        self.logger = logging.getLogger(__name__)
        
        # Model configuration
        self.model_name = config.MODEL_NAME
        self.model_cache_dir = config.MODEL_CACHE_DIR
        self.max_history = config.MAX_HISTORY
        
        # Model components
        self.model = None
        self.tokenizer = None
        self.processor = None
        
        # Conversation history
        self.conversation_history: List[Dict[str, Any]] = []
        self.system_prompt = self._get_system_prompt()
        
        # Performance tracking
        self.inference_count = 0
        self.total_inference_time = 0
        self.last_inference_time = 0
        
        # Initialize model
        self._initialize_model()
    
    def _initialize_model(self):
        """Initialize the multimodal model"""
        try:
            if not TRANSFORMERS_AVAILABLE:
                self.logger.warning("Transformers not available, using mock model")
                return
            
            # Load model and tokenizer
            # Note: This is a placeholder - actual Gemma 3n model loading would be different
            self.logger.info(f"Loading model: {self.model_name}")
            
            # For now, use a basic language model as placeholder
            # In production, this would be the actual Gemma 3n multimodal model
            self.tokenizer = AutoTokenizer.from_pretrained(
                "microsoft/DialoGPT-medium",
                cache_dir=self.model_cache_dir
            )
            
            self.model = AutoModelForCausalLM.from_pretrained(
                "microsoft/DialoGPT-medium",
                cache_dir=self.model_cache_dir
            )
            
            # Set padding token
            if self.tokenizer.pad_token is None:
                self.tokenizer.pad_token = self.tokenizer.eos_token
            
            self.logger.info("Model loaded successfully")
            
        except Exception as e:
            self.logger.error(f"Error loading model: {e}")
            self.model = None
            self.tokenizer = None
    
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
        """Generate response from input data"""
        if self.model is None or self.tokenizer is None:
            return self._mock_response(input_data)
        
        try:
            # Prepare conversation context
            context = self._build_context(input_data)
            
            # Tokenize input
            inputs = self.tokenizer.encode(context, return_tensors="pt")
            
            # Generate response
            with torch.no_grad():
                outputs = self.model.generate(
                    inputs,
                    max_length=inputs.shape[1] + 100,
                    num_return_sequences=1,
                    temperature=0.7,
                    pad_token_id=self.tokenizer.eos_token_id,
                    do_sample=True
                )
            
            # Decode response
            response = self.tokenizer.decode(outputs[0][inputs.shape[1]:], skip_special_tokens=True)
            
            # Clean up response
            response = response.strip()
            if not response:
                response = "I understand."
            
            return response
            
        except Exception as e:
            self.logger.error(f"Error generating response: {e}")
            return "I apologize, but I'm having trouble generating a response right now."
    
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
    
    def _build_context(self, input_data: Dict[str, Any]) -> str:
        """Build conversation context for the model"""
        context_parts = [self.system_prompt]
        
        # Add recent conversation history
        for msg in self.conversation_history[-5:]:  # Last 5 messages
            if msg['type'] == 'user':
                context_parts.append(f"User: {msg['content']}")
            elif msg['type'] == 'assistant':
                context_parts.append(f"Assistant: {msg['content']}")
        
        # Add current input
        current_input = []
        if input_data.get('text'):
            current_input.append(f"Text: {input_data['text']}")
        if input_data.get('image_description'):
            current_input.append(f"Image: {input_data['image_description']}")
        if input_data.get('audio_description'):
            current_input.append(f"Audio: {input_data['audio_description']}")
        
        if current_input:
            context_parts.append(f"User: {' | '.join(current_input)}")
        
        context_parts.append("Assistant:")
        
        return "\n".join(context_parts)
    
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
            'model_loaded': self.model is not None,
            'inference_count': self.inference_count,
            'total_inference_time': self.total_inference_time,
            'avg_inference_time': avg_inference_time,
            'last_inference_time': self.last_inference_time,
            'conversation_length': len(self.conversation_history),
            'max_history': self.max_history
        }