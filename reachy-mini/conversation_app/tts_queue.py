#!/usr/bin/env python3
"""
Text-to-Speech Queue Manager using piper-gpl

This module provides a background TTS queue that:
1. Detects text between "..." in responses
2. Uses piper-gpl to convert text to speech
3. Manages a background audio playback queue
4. Can clear the queue when needed (e.g., when user sends new message)

Requirements:
    - piper-gpl installed (https://github.com/OHF-Voice/piper-gpl)
    - aplay or other audio player for playback
"""

import asyncio
import re
import subprocess
import tempfile
import traceback
from pathlib import Path
from typing import Optional, List
import threading
from queue import Queue, Empty
import os
from dotenv import load_dotenv

# Load environment variables from .env file if available
load_dotenv()


class TTSQueue:
    """Manages text-to-speech conversion and playback queue."""
    
    def __init__(self, piper_executable: str = "piper", voice_model: Optional[str] = None, 
                 audio_device: Optional[str] = None):
        """
        Initialize TTS queue.
        
        Args:
            piper_executable: Path to piper executable
            voice_model: Voice model path (required for piper)
            audio_device: ALSA device for audio playback (e.g., "plughw:CARD=Array,DEV=0")
                         If None, uses default device
        """
        self.piper_executable = piper_executable
        self.audio_device = audio_device
        
        # Model is required for piper
        if voice_model is None:
            # Try to find a default model
            voice_model = self._find_default_model()
            if voice_model is None:
                raise ValueError(
                    "Voice model is required. Please specify a model path or install a default model.\n"
                    "Download models from: https://github.com/rhasspy/piper/releases"
                )
        
        self.voice_model = voice_model
        self.audio_queue = Queue()
        self.playback_thread = None
        self.is_playing = False
        self.should_stop = False
        self.current_process = None
        self.temp_dir = tempfile.mkdtemp(prefix="tts_")
        
        # Check if piper is available
        self._check_piper_available()
        
        # Start playback thread
        self._start_playback_thread()
    
    def _find_default_model(self) -> Optional[str]:
        """Try to find a default piper model."""
        # Common locations for piper models
        possible_locations = [
            Path(__file__).parent / "tts-models",  # Local tts-models folder
            Path.home() / ".local" / "share" / "piper" / "models",
            Path("/usr/share/piper/models"),
            Path("/usr/local/share/piper/models"),
            Path.home() / "piper" / "models",
        ]
        
        for location in possible_locations:
            if location.exists():
                # Look for .onnx model files (both in subdirectories and directly in the folder)
                # First try files directly in the location
                for model_file in location.glob("*.onnx"):
                    print(f"✓ Found default model: {model_file}")
                    # For piper, we need to specify the path WITHOUT the .onnx extension
                    model_path = str(model_file.with_suffix(''))
                    return model_path
                
                # Then try subdirectories
                for model_file in location.rglob("*.onnx"):
                    if model_file.parent != location:  # Skip files we already checked
                        print(f"✓ Found default model: {model_file}")
                        # For piper, we need to specify the path WITHOUT the .onnx extension
                        model_path = str(model_file.with_suffix(''))
                        return model_path
        
        return None
    
    def _check_piper_available(self):
        """Check if piper is available."""
        try:
            result = subprocess.run(
                [self.piper_executable, "--version"],
                capture_output=True,
                text=True,
                timeout=5
            )
            if result.returncode == 0:
                print(f"✓ piper found: {result.stdout.strip()}")
            else:
                print(f"⚠️  piper executable found but returned error")
        except FileNotFoundError:
            print(f"⚠️  piper not found at '{self.piper_executable}'")
            print(f"   Please install from: https://github.com/OHF-Voice/piper-gpl")
        except Exception as e:
            print(f"⚠️  Error checking piper: {e}")
    
    def _start_playback_thread(self):
        """Start the background playback thread."""
        self.playback_thread = threading.Thread(target=self._playback_worker, daemon=True)
        self.playback_thread.start()
    
    def _playback_worker(self):
        """Background worker that processes the audio queue."""
        while not self.should_stop:
            try:
                # Get next audio file from queue (with timeout to allow checking should_stop)
                audio_file = self.audio_queue.get(timeout=0.5)
                
                if audio_file is None:  # Poison pill to stop
                    break
                
                # Play the audio file
                self._play_audio(audio_file)
                
                # Clean up the temporary file
                try:
                    os.unlink(audio_file)
                except Exception as e:
                    print(f"⚠️  Error deleting temp file {audio_file}: {e}")
                
                self.audio_queue.task_done()
                
            except Empty:
                continue
            except Exception as e:
                print(f"⚠️  Error in playback worker: {e}")
    
    def _play_audio(self, audio_file: str):
        """Play an audio file using aplay."""
        try:
            self.is_playing = True
            print(f"🔊 Playing audio: {audio_file}")
            
            # Check if file exists and has content
            if not os.path.exists(audio_file):
                print(f"⚠️  Audio file does not exist: {audio_file}")
                return
            
            file_size = os.path.getsize(audio_file)
            print(f"   File size: {file_size} bytes")
            
            if file_size == 0:
                print(f"⚠️  Audio file is empty: {audio_file}")
                return
            
            # Build aplay command
            cmd = ["aplay"]
            if self.audio_device:
                cmd.extend(["-D", self.audio_device])
            cmd.append(audio_file)
            
            # Use aplay to play the WAV file
            self.current_process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE
            )
            
            # Wait for playback to complete
            stdout, stderr = self.current_process.communicate()
            
            if self.current_process.returncode != 0:
                print(f"⚠️  aplay returned error code: {self.current_process.returncode}")
                if stderr:
                    print(f"   stderr: {stderr.decode('utf-8', errors='ignore')}")
            else:
                print(f"   ✓ Playback completed")
            
            self.current_process = None
            
        except Exception as e:
            print(f"⚠️  Error playing audio: {e}")
            import traceback
            traceback.print_exc()
        finally:
            self.is_playing = False
    
    def text_to_speech(self, text: str) -> Optional[str]:
        """
        Convert text to speech using piper.
        
        Args:
            text: Text to convert to speech
            
        Returns:
            Path to generated WAV file, or None if conversion failed
        """
        if not text.strip():
            return None
        
        try:
            # Create a temporary file for the output
            temp_file = tempfile.NamedTemporaryFile(
                mode='w+b',
                suffix='.wav',
                dir=self.temp_dir,
                delete=False
            )
            temp_file.close()
            output_path = temp_file.name
            
            # Build piper command
            cmd = [self.piper_executable]
            
            # Model is required
            cmd.extend(["--model", self.voice_model])
            
            cmd.extend(["--output_file", output_path])
            
            # Run piper with text as input
            result = subprocess.run(
                cmd,
                input=text.encode('utf-8'),
                capture_output=True,
                timeout=30
            )
            
            if result.returncode == 0 and os.path.exists(output_path):
                return output_path
            else:
                print(f"⚠️  piper conversion failed: {result.stderr.decode('utf-8', errors='ignore')}")
                if os.path.exists(output_path):
                    os.unlink(output_path)
                return None
                
        except Exception as e:
            print(f"⚠️  Error in text_to_speech: {e}")
            return None
    
    def extract_quoted_text(self, text: str) -> List[str]:
        """
        Extract text between "..." from the response.
        
        Args:
            text: Input text containing quoted segments
            
        Returns:
            List of quoted text segments
        """
        # Find all text between "..."
        pattern = r'"([^"]*)"'
        matches = re.findall(pattern, text)
        return [match.strip() for match in matches if match.strip()]
    
    def enqueue_text(self, text: str):
        """
        Extract quoted text and enqueue for TTS playback.
        If no quotes are found, treat the entire text as speech.
        
        Args:
            text: Text that may contain quoted segments to vocalize, or plain text
        """
        # Extract quoted segments
        quoted_texts = self.extract_quoted_text(text)
        
        # If no quoted text found, use the entire text as-is
        if not quoted_texts:
            if text.strip():
                quoted_texts = [text.strip()]
            else:
                return
        
        print(f"🔊 Enqueueing {len(quoted_texts)} TTS segment(s)...")
        
        for quoted_text in quoted_texts:
            # Convert to speech
            audio_file = self.text_to_speech(quoted_text)
            
            if audio_file:
                # Add to playback queue
                self.audio_queue.put(audio_file)
                print(f"   ✓ Queued: \"{quoted_text[:50]}...\"" if len(quoted_text) > 50 else f"   ✓ Queued: \"{quoted_text}\"")
    
    def clear_queue(self):
        """Clear all pending audio from the queue."""
        # Clear the queue
        while not self.audio_queue.empty():
            try:
                audio_file = self.audio_queue.get_nowait()
                # Clean up the temporary file
                if audio_file and os.path.exists(audio_file):
                    try:
                        os.unlink(audio_file)
                    except Exception:
                        pass
                self.audio_queue.task_done()
            except Empty:
                break
        
        # Stop current playback
        if self.current_process:
            try:
                self.current_process.terminate()
                self.current_process.wait(timeout=1)
            except Exception:
                try:
                    self.current_process.kill()
                except Exception:
                    pass
            self.current_process = None
        
        print("🔇 TTS queue cleared")
    
    def cleanup(self):
        """Clean up resources."""
        # Stop playback thread
        self.should_stop = True
        self.audio_queue.put(None)  # Poison pill
        
        # Clear any remaining audio
        self.clear_queue()
        
        # Wait for thread to finish
        if self.playback_thread and self.playback_thread.is_alive():
            self.playback_thread.join(timeout=2)
        
        # Clean up temp directory
        try:
            import shutil
            shutil.rmtree(self.temp_dir, ignore_errors=True)
        except Exception:
            pass


# Async wrapper for use in async applications
class AsyncTTSQueue:
    """Async wrapper for TTSQueue."""
    
    def __init__(self, piper_executable: str = "piper", voice_model: Optional[str] = None,
                 audio_device: Optional[str] = None):
        self.tts_queue = TTSQueue(piper_executable, voice_model, audio_device)
    
    async def enqueue_text(self, text: str):
        """Enqueue text for TTS (async version)."""
        # Run in thread pool to avoid blocking
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(None, self.tts_queue.enqueue_text, text)
    
    async def clear_queue(self):
        """Clear the queue (async version)."""
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(None, self.tts_queue.clear_queue)
    
    def cleanup(self):
        """Clean up resources."""
        self.tts_queue.cleanup()


# Test function
async def test_tts():
    """Test the TTS queue."""
    print("Testing TTS Queue...")
    
    # Get model from environment or use default search
    model_path = os.environ.get("PIPER_MODEL")
    audio_device = os.environ.get("AUDIO_DEVICE", "sysdefault")
    
    try:
        tts = AsyncTTSQueue(voice_model=model_path, audio_device=audio_device)
    except ValueError as e:
        print(f"\n❌ Error: {e}")
        print("\nTo test TTS, either:")
        print("  1. Set PIPER_MODEL environment variable:")
        print("     export PIPER_MODEL=/path/to/model.onnx")
        print("  2. Install a model to a default location:")
        print("     ~/.local/share/piper/models/")
        print("\nDownload models from: https://github.com/rhasspy/piper/releases")
        return
    
    # Test text with quotes
    test_text = 'The robot says "Hello, I am ready to help you!" and also "How can I assist you today?"'
    
    print(f"\nTest text: {test_text}\n")
    
    await tts.enqueue_text(test_text)
    
    # Wait for playback
    print("\nWaiting for playback to complete...")
    await asyncio.sleep(10)
    
    # Clear queue
    print("\nClearing queue...")
    await tts.clear_queue()
    
    # Cleanup
    tts.cleanup()
    
    print("\n✓ Test complete")


if __name__ == "__main__":
    asyncio.run(test_tts())
