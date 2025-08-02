#!/usr/bin/env python3
"""Test script for Piper TTS integration"""

import asyncio
import os
import tempfile
from src.config import Config
from src.queue_manager.queue_manager import QueueManager

async def test_piper_tts():
    """Test Piper TTS functionality"""
    # Create test config
    config = Config()
    config.TTS_ENGINE = "piper"
    
    # Create queue manager
    qm = QueueManager(config)
    
    # Test text extraction
    test_text = 'The assistant said "Hello, this is a test of Piper TTS" and then continued.'
    quoted = qm._extract_quoted_text(test_text)
    print(f"Extracted quoted text: {quoted}")
    
    # Test audio generation
    print(f"\nGenerating audio with {config.TTS_ENGINE} engine...")
    audio_file = await qm._generate_audio(quoted)
    
    if audio_file and os.path.exists(audio_file):
        print(f"Audio file generated: {audio_file}")
        print(f"File size: {os.path.getsize(audio_file)} bytes")
        
        # Test playback
        print("\nPlaying audio...")
        await qm._play_audio(audio_file)
        
        # Clean up
        os.unlink(audio_file)
        print("Test completed successfully!")
    else:
        print("Failed to generate audio file")
    
    # Clean up temp directory
    import shutil
    shutil.rmtree(qm.temp_dir)

if __name__ == "__main__":
    asyncio.run(test_piper_tts())