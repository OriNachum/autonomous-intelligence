#!/usr/bin/env python3
"""
Speech Handler Module

This module handles speech output through TTS, managing:
- TTS queue initialization with reSpeaker device
- Speech item processing from conversation parser
- Playback queue management

Integrates with AsyncTTSQueue to play speech through the reSpeaker device.
"""

import logging
import os
from typing import Optional
from .tts_queue import AsyncTTSQueue

logger = logging.getLogger(__name__)


class SpeechHandler:
    """Handles speech output through TTS."""
    
    def __init__(self, 
                 piper_executable: str = "piper",
                 voice_model: Optional[str] = None,
                 audio_device: Optional[str] = None):
        """
        Initialize the speech handler.
        
        Args:
            piper_executable: Path to piper executable
            voice_model: Voice model path (if None, uses PIPER_MODEL env var or auto-detect)
            audio_device: ALSA device for audio playback (if None, uses AUDIO_DEVICE env var)
        """
        # Get configuration from environment if not provided
        if voice_model is None:
            voice_model = os.environ.get("PIPER_MODEL")
        
        if audio_device is None:
            audio_device = os.environ.get("AUDIO_DEVICE", "plughw:CARD=Array,DEV=0")
        
        logger.info(f"Initializing speech handler...")
        logger.info(f"  Voice model: {voice_model or 'auto-detect'}")
        logger.info(f"  Audio device: {audio_device}")
        
        try:
            self.tts_queue = AsyncTTSQueue(
                piper_executable=piper_executable,
                voice_model=voice_model,
                audio_device=audio_device
            )
            logger.info("✓ Speech handler initialized")
        except Exception as e:
            logger.error(f"❌ Failed to initialize TTS queue: {e}")
            raise
    
    def _normalize_text(self, text: str) -> str:
        """
        Normalize text for TTS:
        1. Decode literal unicode escapes (e.g. \\u2019 -> ')
        2. Replace smart quotes with straight quotes
        """
        if not text:
            return text
        
        # 1. Decode literal Unicode escapes like \\u2019
        # Use a regex to find patterns like \uXXXX and decode them
        import re
        def decode_unicode_escape(match):
            """Decode a single \\uXXXX escape sequence."""
            try:
                hex_code = match.group(1)
                return chr(int(hex_code, 16))
            except (ValueError, OverflowError):
                # If invalid, return original
                return match.group(0)
        
        text = re.sub(r'\\u([0-9a-fA-F]{4})', decode_unicode_escape, text)
        
        # 2. Replace smart quotes with straight quotes using explicit Unicode codes
        # Left single quote (U+2018) and right single quote (U+2019) -> straight apostrophe (U+0027)
        text = text.replace('\u2018', "'").replace('\u2019', "'")
        # Left double quote (U+201C) and right double quote (U+201D) -> straight quote (U+0022)
        text = text.replace('\u201C', '"').replace('\u201D', '"')
        
        return text

    async def speak(self, text: str):
        """
        Queue text for speech output.
        
        Args:
            text: Text to speak (can include quotes or be plain text)
        """
        if not text or not text.strip():
            return
            
        # Normalize text (fix escapes and quotes)
        text = self._normalize_text(text)
        
        logger.debug(f"Queueing speech: {text[:50]}..." if len(text) > 50 else f"Queueing speech: {text}")
        
        try:
            await self.tts_queue.enqueue_text(text)
        except Exception as e:
            logger.error(f"❌ Error queueing speech: {e}")
    
    async def clear(self):
        """Clear all pending speech from the queue."""
        logger.debug("Clearing speech queue")
        try:
            await self.tts_queue.clear_queue()
        except Exception as e:
            logger.error(f"❌ Error clearing speech queue: {e}")
    
    def cleanup(self):
        """Clean up resources."""
        logger.debug("Cleaning up speech handler")
        try:
            self.tts_queue.cleanup()
        except Exception as e:
            logger.error(f"❌ Error during speech handler cleanup: {e}")
