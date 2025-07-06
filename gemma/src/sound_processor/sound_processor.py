"""Sound processing loop with VAD and wake word detection"""

import asyncio
import logging
import numpy as np
import pyaudio
from typing import Optional, Dict, Any
import threading
import time
from queue import Queue as ThreadQueue

from .vad_detector import VADDetector
from .wake_word_detector import WakeWordDetector
from ..event_system import EventProducer, EventType, AudioEvent
from ..config import Config

class SoundProcessor:
    """Sound processing with VAD and wake word detection"""
    
    def __init__(self, config: Config):
        self.config = config
        self.logger = logging.getLogger(__name__)
        
        # Audio configuration
        self.sample_rate = config.AUDIO_SAMPLE_RATE
        self.channels = config.AUDIO_CHANNELS
        self.chunk_size = config.AUDIO_CHUNK_SIZE
        self.format = pyaudio.paFloat32
        
        # Audio processing
        self.vad_detector = VADDetector(
            model_path=config.VAD_MODEL_PATH,
            sample_rate=self.sample_rate
        )
        self.wake_word_detector = WakeWordDetector(
            wake_words=list(config.WAKE_WORDS),
            sample_rate=self.sample_rate
        )
        
        # Event system
        self.event_producer = EventProducer(config, "sound_processor")
        
        # PyAudio
        self.audio = None
        self.stream = None
        self.running = False
        
        # Audio processing
        self.audio_queue = ThreadQueue(maxsize=50)
        self.processing_active = False
        
        # Threading
        self.capture_thread: Optional[threading.Thread] = None
        
        # State tracking
        self.current_speech_active = False
        self.current_wake_word_active = False
        self.last_audio_time = 0
        
        # Performance metrics
        self.processed_chunks = 0
        self.processing_times = []
        self.vad_detections = 0
        self.wake_word_detections = 0
    
    async def start(self):
        """Start sound processing"""
        self.logger.info("Starting sound processor")
        
        # Connect to event system
        await self.event_producer.connect()
        
        # Initialize audio
        if not self._initialize_audio():
            self.logger.error("Failed to initialize audio")
            return False
        
        self.running = True
        self.processing_active = True
        
        # Start capture thread
        self.capture_thread = threading.Thread(target=self._capture_loop, daemon=True)
        self.capture_thread.start()
        
        # Start processing loop
        asyncio.create_task(self._processing_loop())
        
        self.logger.info("Sound processor started")
        return True
    
    async def stop(self):
        """Stop sound processing"""
        self.logger.info("Stopping sound processor")
        
        self.running = False
        self.processing_active = False
        
        # Wait for capture thread
        if self.capture_thread and self.capture_thread.is_alive():
            self.capture_thread.join(timeout=2.0)
        
        # Close audio stream
        if self.stream:
            self.stream.stop_stream()
            self.stream.close()
            self.stream = None
        
        # Close PyAudio
        if self.audio:
            self.audio.terminate()
            self.audio = None
        
        # Disconnect from event system
        await self.event_producer.disconnect()
        
        self.logger.info("Sound processor stopped")
    
    def _initialize_audio(self) -> bool:
        """Initialize PyAudio"""
        try:
            self.audio = pyaudio.PyAudio()
            
            # Find input device
            device_index = None
            for i in range(self.audio.get_device_count()):
                device_info = self.audio.get_device_info_by_index(i)
                if device_info['maxInputChannels'] > 0:
                    device_index = i
                    break
            
            if device_index is None:
                self.logger.error("No input audio device found")
                return False
            
            # Open stream
            self.stream = self.audio.open(
                format=self.format,
                channels=self.channels,
                rate=self.sample_rate,
                input=True,
                input_device_index=device_index,
                frames_per_buffer=self.chunk_size
            )
            
            self.logger.info(f"Audio initialized: {self.sample_rate}Hz, {self.channels} channels, chunk size {self.chunk_size}")
            return True
            
        except Exception as e:
            self.logger.error(f"Error initializing audio: {e}")
            return False
    
    def _capture_loop(self):
        """Audio capture loop running in separate thread"""
        while self.running:
            try:
                # Read audio data
                audio_data = self.stream.read(self.chunk_size, exception_on_overflow=False)
                
                # Convert to numpy array
                audio_array = np.frombuffer(audio_data, dtype=np.float32)
                
                # Add to processing queue
                if not self.audio_queue.full():
                    self.audio_queue.put(audio_array)
                else:
                    # Drop oldest if queue is full
                    try:
                        self.audio_queue.get_nowait()
                        self.audio_queue.put(audio_array)
                    except:
                        pass
                
                self.last_audio_time = time.time()
                
            except Exception as e:
                self.logger.error(f"Error in audio capture: {e}")
                time.sleep(0.1)
    
    async def _processing_loop(self):
        """Main audio processing loop"""
        while self.processing_active:
            try:
                # Get audio chunk
                audio_chunk = await self._get_audio_chunk()
                if audio_chunk is None:
                    await asyncio.sleep(0.01)
                    continue
                
                # Process audio
                await self._process_audio_chunk(audio_chunk)
                
            except Exception as e:
                self.logger.error(f"Error in processing loop: {e}")
                await asyncio.sleep(0.1)
    
    async def _get_audio_chunk(self) -> Optional[np.ndarray]:
        """Get audio chunk from queue"""
        try:
            if not self.audio_queue.empty():
                return self.audio_queue.get_nowait()
        except:
            pass
        return None
    
    async def _process_audio_chunk(self, audio_chunk: np.ndarray):
        """Process a single audio chunk"""
        start_time = time.time()
        
        try:
            # VAD processing
            is_speech, vad_confidence = self.vad_detector.process_audio(audio_chunk)
            vad_event = self.vad_detector.update_speech_state(is_speech, vad_confidence)
            
            # Update VAD buffer
            self.vad_detector.add_to_buffer(audio_chunk)
            
            # Wake word processing (only if speech is detected)
            wake_word_detected = False
            wake_word_text = None
            wake_word_confidence = 0.0
            
            if is_speech:
                wake_word_detected, wake_word_text, wake_word_confidence = \
                    self.wake_word_detector.process_audio(audio_chunk)
            
            # Send events
            await self._send_audio_events(
                audio_chunk, is_speech, vad_confidence, vad_event,
                wake_word_detected, wake_word_text, wake_word_confidence
            )
            
            # Update statistics
            self.processed_chunks += 1
            if is_speech:
                self.vad_detections += 1
            if wake_word_detected:
                self.wake_word_detections += 1
            
            # Track performance
            processing_time = time.time() - start_time
            self.processing_times.append(processing_time)
            if len(self.processing_times) > 100:
                self.processing_times.pop(0)
                
        except Exception as e:
            self.logger.error(f"Error processing audio chunk: {e}")
    
    async def _send_audio_events(self, audio_chunk: np.ndarray, is_speech: bool, 
                                vad_confidence: float, vad_event: Optional[str],
                                wake_word_detected: bool, wake_word_text: Optional[str],
                                wake_word_confidence: float):
        """Send audio-related events"""
        try:
            # Send audio frame event (optional, for debugging)
            # Uncomment if you want to send raw audio data
            # audio_event = AudioEvent(
            #     event_type=EventType.AUDIO_FRAME,
            #     audio_data=audio_chunk.tobytes(),
            #     confidence=vad_confidence
            # )
            # await self.event_producer.send_event(audio_event)
            
            # Send VAD events
            if vad_event == "speech_started":
                speech_event = AudioEvent(
                    event_type=EventType.SPEECH_DETECTED,
                    confidence=vad_confidence
                )
                await self.event_producer.send_event(speech_event)
                self.current_speech_active = True
                self.logger.debug("Speech started")
                
            elif vad_event == "speech_ended":
                # Get speech audio
                speech_audio = self.vad_detector.get_speech_audio()
                if speech_audio is not None:
                    speech_event = AudioEvent(
                        event_type=EventType.SPEECH_DETECTED,
                        audio_data=speech_audio.tobytes(),
                        confidence=vad_confidence
                    )
                    await self.event_producer.send_event(speech_event)
                
                self.current_speech_active = False
                self.logger.debug("Speech ended")
            
            # Send wake word events
            if wake_word_detected:
                wake_word_event = AudioEvent(
                    event_type=EventType.WAKE_WORD_DETECTED,
                    wake_word=wake_word_text,
                    confidence=wake_word_confidence
                )
                await self.event_producer.send_event(wake_word_event)
                self.current_wake_word_active = True
                self.logger.info(f"Wake word detected: {wake_word_text}")
                
        except Exception as e:
            self.logger.error(f"Error sending audio events: {e}")
    
    def get_status(self) -> Dict[str, Any]:
        """Get sound processor status"""
        avg_processing_time = np.mean(self.processing_times) if self.processing_times else 0
        
        return {
            'running': self.running,
            'processed_chunks': self.processed_chunks,
            'vad_detections': self.vad_detections,
            'wake_word_detections': self.wake_word_detections,
            'current_speech_active': self.current_speech_active,
            'current_wake_word_active': self.current_wake_word_active,
            'last_audio_time': self.last_audio_time,
            'avg_processing_time': avg_processing_time,
            'audio_config': {
                'sample_rate': self.sample_rate,
                'channels': self.channels,
                'chunk_size': self.chunk_size
            },
            'vad_stats': self.vad_detector.get_statistics(),
            'wake_word_stats': self.wake_word_detector.get_statistics()
        }
    
    def get_current_audio(self) -> Optional[np.ndarray]:
        """Get current audio buffer"""
        return self.wake_word_detector.get_buffer_audio()
    
    def reset_state(self):
        """Reset audio processing state"""
        self.vad_detector.reset()
        self.wake_word_detector.reset()
        self.current_speech_active = False
        self.current_wake_word_active = False
        self.logger.info("Audio processing state reset")