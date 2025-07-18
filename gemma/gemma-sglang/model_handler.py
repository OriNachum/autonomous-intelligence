#!/usr/bin/env python3

import asyncio
import base64
import io
import logging
import os
from typing import AsyncGenerator, Dict, List, Optional, Tuple, Union, Any

import numpy as np
from PIL import Image
import requests

logger = logging.getLogger(__name__)

class SGLangGemmaHandler:
    """Handler for Gemma 3n model using SGLang backend."""
    
    def __init__(self):
        self.sglang_url = os.getenv("SGLANG_URL", "http://localhost:30000")
        self.model_name = os.getenv("MODEL_NAME", "gemma3n")
        self.ready = False
        
        # Audio processing settings
        self.enable_audio = os.getenv("ENABLE_AUDIO", "true").lower() == "true"
        self.whisper_model = os.getenv("WHISPER_MODEL", "openai/whisper-base")
        
        logger.info(f"Initializing SGLang handler with URL: {self.sglang_url}")

    async def initialize(self):
        """Initialize the model and check connection to SGLang."""
        try:
            # Test connection to SGLang server
            await self._test_connection()
            self.ready = True
            logger.info("SGLang connection established successfully")
        except Exception as e:
            logger.error(f"Failed to initialize SGLang handler: {e}")
            raise

    async def cleanup(self):
        """Cleanup resources."""
        self.ready = False
        logger.info("SGLang handler cleanup complete")

    def is_ready(self) -> bool:
        """Check if the model is ready for inference."""
        return self.ready

    async def _test_connection(self):
        """Test connection to SGLang server."""
        try:
            # Make a simple health check to SGLang
            url = f"{self.sglang_url}/health"
            response = requests.get(url, timeout=10)
            response.raise_for_status()
            logger.info("SGLang server health check passed")
        except Exception as e:
            logger.error(f"SGLang server not accessible: {e}")
            raise ConnectionError(f"Cannot connect to SGLang server at {self.sglang_url}")

    async def generate(
        self,
        processed_input: Dict[str, Any],
        temperature: float = 0.7,
        max_tokens: int = 2048,
        top_p: float = 1.0,
        stop: Optional[Union[str, List[str]]] = None
    ) -> Tuple[str, Dict[str, int]]:
        """Generate a complete response."""
        
        # Build the input prompt
        prompt = await self._build_prompt(processed_input)
        
        # Prepare request payload for SGLang
        payload = {
            "text": prompt,
            "sampling_params": {
                "temperature": temperature,
                "max_new_tokens": max_tokens,
                "top_p": top_p,
                "stop": stop if stop else []
            }
        }
        
        # Add multimodal data if present
        if processed_input.get("images"):
            payload["image_data"] = processed_input["images"]
        
        try:
            # Make request to SGLang
            response = await self._make_sglang_request("/generate", payload)
            
            # Extract response text and usage info
            response_text = response.get("text", "")
            usage_info = {
                "prompt_tokens": response.get("usage", {}).get("prompt_tokens", 0),
                "completion_tokens": response.get("usage", {}).get("completion_tokens", 0),
                "total_tokens": response.get("usage", {}).get("total_tokens", 0)
            }
            
            return response_text, usage_info
            
        except Exception as e:
            logger.error(f"Error in SGLang generation: {e}")
            raise

    async def generate_stream(
        self,
        processed_input: Dict[str, Any],
        temperature: float = 0.7,
        max_tokens: int = 2048,
        top_p: float = 1.0,
        stop: Optional[Union[str, List[str]]] = None
    ) -> AsyncGenerator[Tuple[str, Optional[str]], None]:
        """Generate a streaming response."""
        
        # Build the input prompt
        prompt = await self._build_prompt(processed_input)
        
        # Prepare request payload for SGLang streaming
        payload = {
            "text": prompt,
            "sampling_params": {
                "temperature": temperature,
                "max_new_tokens": max_tokens,
                "top_p": top_p,
                "stop": stop if stop else []
            },
            "stream": True
        }
        
        # Add multimodal data if present
        if processed_input.get("images"):
            payload["image_data"] = processed_input["images"]
        
        try:
            # Make streaming request to SGLang
            async for chunk in self._make_sglang_stream_request("/generate", payload):
                token = chunk.get("text", "")
                finish_reason = chunk.get("finish_reason")
                yield token, finish_reason
                
        except Exception as e:
            logger.error(f"Error in SGLang streaming: {e}")
            raise

    async def _build_prompt(self, processed_input: Dict[str, Any]) -> str:
        """Build the final prompt including multimodal content markers."""
        prompt_parts = []
        
        # Add image tokens if images are present
        if processed_input.get("images"):
            for i, _ in enumerate(processed_input["images"]):
                prompt_parts.append(f"<image_{i}>")
        
        # Add audio transcription if audio is present
        if processed_input.get("audio") and self.enable_audio:
            for audio_data in processed_input["audio"]:
                transcription = await self._process_audio(audio_data)
                prompt_parts.append(f"[Audio transcription: {transcription}]")
        
        # Add text content
        if processed_input.get("text"):
            prompt_parts.append(processed_input["text"])
        
        # Add assistant prompt
        prompt_parts.append("assistant:")
        
        return "\n".join(prompt_parts)

    async def _process_audio(self, audio_data: Dict[str, Any]) -> str:
        """Process audio data and return transcription."""
        try:
            # Extract audio from base64 or URL
            audio_content = None
            
            if "data" in audio_data:
                # Base64 encoded audio
                audio_base64 = audio_data["data"]
                if audio_base64.startswith("data:"):
                    # Remove data URL prefix
                    audio_base64 = audio_base64.split(",", 1)[1]
                audio_content = base64.b64decode(audio_base64)
            elif "url" in audio_data:
                # Audio URL
                response = requests.get(audio_data["url"])
                response.raise_for_status()
                audio_content = response.content
            
            if not audio_content:
                return "[Audio processing failed: No valid audio data]"
            
            # Use Whisper for transcription (placeholder - replace with actual Whisper integration)
            # This would integrate with your Whisper setup or use SGLang's audio capabilities
            transcription = await self._transcribe_audio(audio_content)
            return transcription
            
        except Exception as e:
            logger.error(f"Error processing audio: {e}")
            return f"[Audio processing error: {str(e)}]"

    async def _transcribe_audio(self, audio_content: bytes) -> str:
        """Transcribe audio content using Whisper or similar."""
        # Placeholder for actual audio transcription
        # You would integrate with Whisper here or use SGLang's audio capabilities
        logger.warning("Audio transcription not implemented - returning placeholder")
        return "[Audio transcription placeholder - implement Whisper integration]"

    async def _make_sglang_request(self, endpoint: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        """Make a request to SGLang server."""
        import aiohttp
        
        url = f"{self.sglang_url}{endpoint}"
        
        async with aiohttp.ClientSession() as session:
            async with session.post(url, json=payload) as response:
                response.raise_for_status()
                return await response.json()

    async def _make_sglang_stream_request(
        self, 
        endpoint: str, 
        payload: Dict[str, Any]
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """Make a streaming request to SGLang server."""
        import aiohttp
        import json
        
        url = f"{self.sglang_url}{endpoint}"
        
        async with aiohttp.ClientSession() as session:
            async with session.post(url, json=payload) as response:
                response.raise_for_status()
                
                async for line in response.content:
                    line = line.decode('utf-8').strip()
                    if line.startswith('data: '):
                        line = line[6:]  # Remove 'data: ' prefix
                        if line == '[DONE]':
                            break
                        try:
                            chunk = json.loads(line)
                            yield chunk
                        except json.JSONDecodeError:
                            continue

    def _process_image_data(self, image_data: Dict[str, Any]) -> Image.Image:
        """Process image data from URL or base64."""
        try:
            if "url" in image_data:
                if image_data["url"].startswith("data:"):
                    # Base64 data URL
                    header, data = image_data["url"].split(",", 1)
                    image_bytes = base64.b64decode(data)
                else:
                    # Regular URL
                    response = requests.get(image_data["url"])
                    response.raise_for_status()
                    image_bytes = response.content
                
                # Convert to PIL Image
                image = Image.open(io.BytesIO(image_bytes))
                
                # Convert to RGB if necessary
                if image.mode != "RGB":
                    image = image.convert("RGB")
                
                return image
                
        except Exception as e:
            logger.error(f"Error processing image: {e}")
            raise ValueError(f"Failed to process image data: {str(e)}")

    def _encode_image_for_sglang(self, image: Image.Image) -> str:
        """Encode PIL Image for SGLang."""
        # Convert to base64 for transmission to SGLang
        buffer = io.BytesIO()
        image.save(buffer, format="JPEG")
        image_base64 = base64.b64encode(buffer.getvalue()).decode('utf-8')
        return image_base64