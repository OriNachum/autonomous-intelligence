"""Queue manager that handles TTS events and coordinates with TTS engine"""

import asyncio
import logging
import subprocess
import os
from typing import Optional, Dict, Any, List
import tempfile
import re

from .tts_queue import TTSQueue, TTSQueueItem
from ..event_system import EventConsumer, EventProducer, EventType, TTSEvent
from ..config import Config

class QueueManager:
    """Manages TTS queue and coordinates with TTS engine"""
    
    def __init__(self, config: Config):
        self.config = config
        self.logger = logging.getLogger(__name__)
        
        # TTS queue
        self.tts_queue = TTSQueue(
            max_size=config.TTS_QUEUE_MAX_SIZE,
            max_tokens=config.TTS_MAX_TOKENS
        )
        
        # Event handling
        self.event_consumer = EventConsumer(config, "queue_manager")
        self.event_producer = EventProducer(config, "queue_manager")
        
        # Processing state
        self.running = False
        self.current_process: Optional[subprocess.Popen] = None
        
        # TTS engine configuration
        self.tts_engine = config.TTS_ENGINE
        self.temp_dir = tempfile.mkdtemp(prefix="gemma_tts_")
        
        # Register event handlers
        self.event_consumer.register_handler(EventType.QUEUE_SENTENCES, self._handle_queue_sentences)
        self.event_consumer.register_handler(EventType.RESET_QUEUE, self._handle_reset_queue)
    
    async def start(self):
        """Start the queue manager"""
        self.logger.info("Starting TTS queue manager")
        
        # Connect to event system
        await self.event_consumer.connect()
        await self.event_producer.connect()
        
        # Start consuming events
        await self.event_consumer.start_consuming()
        
        self.running = True
        
        # Start processing loop
        asyncio.create_task(self._processing_loop())
        
        self.logger.info("TTS queue manager started")
    
    async def stop(self):
        """Stop the queue manager"""
        self.logger.info("Stopping TTS queue manager")
        
        self.running = False
        
        # Stop current TTS process
        if self.current_process:
            self.current_process.terminate()
            await asyncio.sleep(0.1)
            if self.current_process.poll() is None:
                self.current_process.kill()
        
        # Stop event system
        await self.event_consumer.stop_consuming()
        await self.event_producer.disconnect()
        
        # Clean up temp directory
        try:
            import shutil
            shutil.rmtree(self.temp_dir)
        except:
            pass
        
        self.logger.info("TTS queue manager stopped")
    
    async def _handle_queue_sentences(self, event: TTSEvent):
        """Handle queue sentences event"""
        sentences = event.data.get('sentences', [])
        if sentences:
            await self.tts_queue.add_sentences(sentences)
            self.logger.debug(f"Queued {len(sentences)} sentences")
    
    async def _handle_reset_queue(self, event: TTSEvent):
        """Handle reset queue event"""
        # Stop current TTS process
        if self.current_process:
            self.current_process.terminate()
            await asyncio.sleep(0.1)
            if self.current_process.poll() is None:
                self.current_process.kill()
            self.current_process = None
        
        # Reset the queue
        await self.tts_queue.reset_queue()
        self.logger.info("TTS queue reset")
    
    async def _processing_loop(self):
        """Main processing loop for TTS queue"""
        while self.running:
            try:
                # Check if reset was requested
                if self.tts_queue.is_reset_requested():
                    await self.tts_queue.acknowledge_reset()
                    continue
                
                # Get next item from queue
                item = await self.tts_queue.get_next_item()
                if item is None:
                    await asyncio.sleep(0.1)
                    continue
                
                # Process the item
                await self._process_tts_item(item)
                
            except Exception as e:
                self.logger.error(f"Error in processing loop: {e}")
                await asyncio.sleep(0.1)
    
    async def _process_tts_item(self, item: TTSQueueItem):
        """Process a single TTS item"""
        try:
            # Extract quoted text for TTS
            quoted_text = self._extract_quoted_text(item.text)
            if not quoted_text:
                self.logger.debug(f"No quoted text found in: {item.text}")
                await self.tts_queue.mark_item_complete(item)
                return
            
            # Generate audio file
            audio_file = await self._generate_audio(quoted_text)
            if not audio_file:
                self.logger.error(f"Failed to generate audio for: {quoted_text}")
                await self.tts_queue.mark_item_complete(item)
                return
            
            # Play audio
            await self._play_audio(audio_file)
            
            # Clean up
            try:
                os.unlink(audio_file)
            except:
                pass
            
            # Mark item as complete
            await self.tts_queue.mark_item_complete(item)
            
            # Send completion event
            completion_event = TTSEvent(EventType.TTS_FINISHED)
            completion_event.data['completed_text'] = quoted_text
            await self.event_producer.send_event(completion_event)
            
        except Exception as e:
            self.logger.error(f"Error processing TTS item: {e}")
            await self.tts_queue.mark_item_complete(item)
    
    def _extract_quoted_text(self, text: str) -> str:
        """Extract text within quotes for TTS"""
        # Find all quoted text
        quoted_matches = re.findall(r'"([^"]*)"', text)
        if quoted_matches:
            return ' '.join(quoted_matches)
        return ""
    
    async def _generate_audio(self, text: str) -> Optional[str]:
        """Generate audio file from text"""
        try:
            # Create temporary audio file
            audio_file = os.path.join(self.temp_dir, f"tts_{asyncio.get_event_loop().time()}.wav")
            
            if self.tts_engine == "kokoro":
                # Use KokoroTTS (placeholder - adjust based on actual API)
                cmd = [
                    "python", "-m", "kokoro_tts",
                    "--text", text,
                    "--output", audio_file
                ]
            else:
                # Fallback to espeak
                cmd = [
                    "espeak",
                    "-w", audio_file,
                    text
                ]
            
            # Run TTS command
            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            
            stdout, stderr = await process.communicate()
            
            if process.returncode == 0 and os.path.exists(audio_file):
                return audio_file
            else:
                self.logger.error(f"TTS generation failed: {stderr.decode()}")
                return None
                
        except Exception as e:
            self.logger.error(f"Error generating audio: {e}")
            return None
    
    async def _play_audio(self, audio_file: str):
        """Play audio file"""
        try:
            # Use aplay or similar to play audio
            cmd = ["aplay", audio_file]
            
            self.current_process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            
            # Wait for playback to complete
            await self.current_process.wait()
            self.current_process = None
            
        except Exception as e:
            self.logger.error(f"Error playing audio: {e}")
            self.current_process = None
    
    def get_queue_status(self) -> Dict[str, Any]:
        """Get current queue status"""
        return self.tts_queue.get_status()