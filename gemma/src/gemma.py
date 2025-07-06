"""Main Gemma application"""

import asyncio
import logging
import signal
import sys
from typing import Optional

from .config import Config
from .logging_config import setup_logging
from .event_system import EventManager
from .queue_manager import QueueManager
from .camera_processor import CameraProcessor
from .sound_processor import SoundProcessor
from .text_processor import TextProcessor
from .main_loop import MainLoop

class GemmaApplication:
    """Main Gemma application coordinator"""
    
    def __init__(self, config: Optional[Config] = None):
        self.config = config or Config.from_env()
        self.logger = setup_logging(self.config.LOG_LEVEL, self.config.LOG_FORMAT)
        
        # Core components
        self.event_manager = EventManager(self.config)
        self.queue_manager = QueueManager(self.config)
        self.camera_processor = CameraProcessor(self.config)
        self.sound_processor = SoundProcessor(self.config)
        self.text_processor = TextProcessor(self.config)
        self.main_loop = MainLoop(self.config)
        
        # Application state
        self.running = False
        self.components = [
            self.event_manager,
            self.queue_manager,
            self.camera_processor,
            self.sound_processor,
            self.text_processor,
            self.main_loop
        ]
        
        # Setup signal handlers
        self._setup_signal_handlers()
    
    def _setup_signal_handlers(self):
        """Setup signal handlers for graceful shutdown"""
        def signal_handler(signum, frame):
            self.logger.info(f"Received signal {signum}, initiating shutdown...")
            asyncio.create_task(self.stop())
        
        signal.signal(signal.SIGINT, signal_handler)
        signal.signal(signal.SIGTERM, signal_handler)
    
    async def start(self):
        """Start all Gemma components"""
        self.logger.info("Starting Gemma application")
        
        try:
            # Start components in order
            self.logger.info("Starting event manager...")
            await self.event_manager.start()
            
            # Small delay to ensure event system is ready
            await asyncio.sleep(0.1)
            
            self.logger.info("Starting queue manager...")
            await self.queue_manager.start()
            
            self.logger.info("Starting camera processor...")
            camera_started = await self.camera_processor.start()
            if not camera_started:
                self.logger.warning("Camera processor failed to start")
            
            self.logger.info("Starting sound processor...")
            sound_started = await self.sound_processor.start()
            if not sound_started:
                self.logger.warning("Sound processor failed to start")
            
            self.logger.info("Starting text processor...")
            await self.text_processor.start()
            
            self.logger.info("Starting main loop...")
            await self.main_loop.start()
            
            self.running = True
            self.logger.info("Gemma application started successfully")
            
            # Print status
            await self._print_startup_status()
            
            return True
            
        except Exception as e:
            self.logger.error(f"Error starting Gemma application: {e}")
            await self.stop()
            return False
    
    async def stop(self):
        """Stop all Gemma components"""
        if not self.running:
            return
        
        self.logger.info("Stopping Gemma application")
        self.running = False
        
        # Stop components in reverse order
        try:
            await self.main_loop.stop()
            await self.text_processor.stop()
            await self.sound_processor.stop()
            await self.camera_processor.stop()
            await self.queue_manager.stop()
            await self.event_manager.stop()
            
            self.logger.info("Gemma application stopped")
            
        except Exception as e:
            self.logger.error(f"Error stopping Gemma application: {e}")
    
    async def run(self):
        """Run the application until stopped"""
        if not await self.start():
            return
        
        try:
            # Keep running until stopped
            while self.running:
                await asyncio.sleep(1.0)
                
                # Optional: Print periodic status
                # await self._print_periodic_status()
                
        except KeyboardInterrupt:
            self.logger.info("Keyboard interrupt received")
        except Exception as e:
            self.logger.error(f"Error in main run loop: {e}")
        finally:
            await self.stop()
    
    async def _print_startup_status(self):
        """Print startup status information"""
        print("\n" + "="*60)
        print("           GEMMA MULTIMODAL AI ASSISTANT")
        print("="*60)
        print(f"Event Manager:    {'✓ Running' if self.event_manager.running else '✗ Failed'}")
        print(f"Queue Manager:    {'✓ Running' if self.queue_manager.running else '✗ Failed'}")
        print(f"Camera Processor: {'✓ Running' if self.camera_processor.running else '✗ Failed'}")
        print(f"Sound Processor:  {'✓ Running' if self.sound_processor.running else '✗ Failed'}")
        print(f"Text Processor:   {'✓ Running' if self.text_processor.running else '✗ Failed'}")
        print(f"Main Loop:        {'✓ Running' if self.main_loop.running else '✗ Failed'}")
        print("="*60)
        print()
        
        # Print configuration
        print("Configuration:")
        print(f"  Camera: {self.config.CAMERA_WIDTH}x{self.config.CAMERA_HEIGHT} @ {self.config.CAMERA_FPS}fps")
        print(f"  Audio:  {self.config.AUDIO_SAMPLE_RATE}Hz, {self.config.AUDIO_CHANNELS} channels")
        print(f"  Model:  {self.config.MODEL_NAME}")
        print(f"  TTS:    {self.config.TTS_ENGINE}")
        print("="*60)
        print()
    
    async def _print_periodic_status(self):
        """Print periodic status (optional)"""
        # This could be used for debugging or monitoring
        pass
    
    def get_status(self) -> dict:
        """Get application status"""
        return {
            'running': self.running,
            'config': {
                'camera_resolution': f"{self.config.CAMERA_WIDTH}x{self.config.CAMERA_HEIGHT}",
                'camera_fps': self.config.CAMERA_FPS,
                'audio_sample_rate': self.config.AUDIO_SAMPLE_RATE,
                'model_name': self.config.MODEL_NAME,
                'tts_engine': self.config.TTS_ENGINE
            },
            'components': {
                'event_manager': self.event_manager.running if hasattr(self.event_manager, 'running') else False,
                'queue_manager': self.queue_manager.running if hasattr(self.queue_manager, 'running') else False,
                'camera_processor': self.camera_processor.running if hasattr(self.camera_processor, 'running') else False,
                'sound_processor': self.sound_processor.running if hasattr(self.sound_processor, 'running') else False,
                'text_processor': self.text_processor.running if hasattr(self.text_processor, 'running') else False,
                'main_loop': self.main_loop.running if hasattr(self.main_loop, 'running') else False
            }
        }

async def main():
    """Main entry point"""
    try:
        # Create and run application
        app = GemmaApplication()
        await app.run()
        
    except Exception as e:
        logging.error(f"Fatal error: {e}")
        sys.exit(1)

if __name__ == "__main__":
    asyncio.run(main())