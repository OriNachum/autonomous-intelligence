#!/usr/bin/env python3
"""
Hearing Event Emitter - Service that detects speech using VAD and emits events

This service listens to audio input, detects speech using Voice Activity Detection,
and emits events via Unix Domain Socket to connected clients.

Usage:
    python3 hearing_event_emitter.py --device ReSpeaker --language en
"""

import pyaudio
import wave
import time
import numpy as np
import os
import socket
import sys
import logging
import json
import argparse
from datetime import datetime
from dotenv import load_dotenv
import asyncio
from collections import deque
from pathlib import Path
import torch

# Import our custom modules
from vad_detector import VADDetector
from whisper_stt import WhisperSTT

# Set up logging
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)
logger.info("Hearing Event Emitter starting...")

# Load environment variables
load_dotenv()
logger.debug("Environment variables loaded")


class HearingEventEmitter:
    """Service that detects speech and emits events via Unix Domain Socket"""
    
    def __init__(self, device_name=None, language='en'):
        logger.info("Initializing HearingEventEmitter")
        
        # Configuration from environment or defaults
        self.device_name = (device_name or os.getenv('AUDIO_DEVICE_NAME', 'default')).lower()
        self.language = language
        self.socket_path = os.getenv('SOCKET_PATH', '/tmp/reachy_sockets/hearing.sock')
        
        # Audio configuration
        self.rate = int(os.getenv('SAMPLE_RATE', '16000'))
        self.chunk_duration_ms = int(os.getenv('CHUNK_DURATION_MS', '30'))
        self.chunk_size = int(self.rate * self.chunk_duration_ms / 1000)
        
        # VAD configuration
        vad_aggressiveness = int(os.getenv('VAD_AGGRESSIVENESS', '3'))
        self.vad = VADDetector(aggressiveness=vad_aggressiveness, sample_rate=self.rate)
        
        # Speech detection configuration
        self.min_silence_duration = float(os.getenv('MIN_SILENCE_DURATION', '0.5'))
        self.post_speech_buffer_duration = float(os.getenv('POST_SPEECH_BUFFER_DURATION', '0.5'))  # 0.5 seconds after speech ends
        self.lower_threshold = int(os.getenv('SPEECH_THRESHOLD_LOWER', '1500'))
        self.upper_threshold = int(os.getenv('SPEECH_THRESHOLD_UPPER', '2500'))
        self.min_audio_bytes = 4000
        
        # Partial transcription configuration
        self.enable_partial_transcription = os.getenv('ENABLE_PARTIAL_TRANSCRIPTION', 'true').lower() == 'true'
        self.partial_transcription_interval = float(os.getenv('PARTIAL_TRANSCRIPTION_INTERVAL', '1.0'))  # seconds
        self.min_partial_chunks = int(os.getenv('MIN_PARTIAL_CHUNKS', '10'))  # Minimum chunks before partial transcription
        
        # Buffers
        buffer_size = int(os.getenv('AUDIO_BUFFER_SIZE', '100'))
        self.audio_buffer = deque(maxlen=buffer_size)
        self.speech_buffer = []
        self.post_speech_buffer = []  # Buffer for audio after speech ends
        
        # State
        self.speech_detected = False
        self.silence_start_time = None
        self.start_time = None
        self.speech_events = 0
        self.processing_lock = asyncio.Lock()
        self.collecting_post_speech = False
        
        # Partial transcription state
        self.last_partial_transcription_time = None
        self.partial_transcription_in_progress = False
        self.last_partial_text = ""
        
        # Whisper STT configuration
        whisper_model_size = os.getenv('WHISPER_MODEL_SIZE', 'base')
        
        # Auto-detect CUDA availability
        cuda_available = torch.cuda.is_available()
        default_device = 'cuda' if cuda_available else 'cpu'
        whisper_device = os.getenv('WHISPER_DEVICE', default_device)
        
        # Set compute_type based on device
        if whisper_device == 'cuda':
            default_compute_type = 'float16'
        else:
            default_compute_type = 'int8'
        whisper_compute_type = os.getenv('WHISPER_COMPUTE_TYPE', default_compute_type)
        
        logger.info(f"CUDA available: {cuda_available}")
        logger.info(f"Whisper will use device: {whisper_device} with compute_type: {whisper_compute_type}")
        
        self.whisper = WhisperSTT(
            model_size=whisper_model_size,
            device=whisper_device,
            compute_type=whisper_compute_type,
            language=self.language
        )
        
        # Socket setup
        self.server_socket = None
        self.clients = []
        self.setup_socket_server()
        
        # Audio setup
        self.p = pyaudio.PyAudio()
        self.stream = None
        self.input_device_index = None
        self.num_channels = 1  # Default to mono
        self.use_aec_channel = False  # Whether to use AEC channel 0 from 2-channel device
        
        logger.info("HearingEventEmitter initialization complete")
    
    def setup_socket_server(self):
        """Set up Unix Domain Socket server"""
        logger.debug(f"Setting up Unix socket server at {self.socket_path}")
        
        # Create socket directory if it doesn't exist
        socket_dir = os.path.dirname(self.socket_path)
        os.makedirs(socket_dir, exist_ok=True)
        
        # Remove existing socket file if it exists
        if os.path.exists(self.socket_path):
            os.remove(self.socket_path)
        
        # Create socket
        self.server_socket = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self.server_socket.bind(self.socket_path)
        self.server_socket.listen(5)
        self.server_socket.setblocking(False)
        
        # Set permissions
        os.chmod(self.socket_path, 0o666)
        
        logger.info(f"Socket server listening on {self.socket_path}")
    
    def initialize_input_device(self):
        """Find and initialize audio input device"""
        wait_times = [1, 2, 4, 8, 16, 32]
        for wait_time in wait_times:
            self.input_device_index = self.find_input_device()
            if self.input_device_index is not None:
                break
            logger.warning(f"Input device not found, retrying in {wait_time} seconds...")
            time.sleep(wait_time)
        else:
            logger.error("Suitable input device not found after multiple attempts")
            raise RuntimeError("Suitable input device not found")
        
        logger.info(f"Using audio device index: {self.input_device_index}")
    
    def find_input_device(self):
        """Search for audio input device by name"""
        logger.info("Searching for input device")
        device_count = self.p.get_device_count()
        logger.info(f"Found {device_count} audio devices")
        
        for i in range(device_count):
            device_info = self.p.get_device_info_by_index(i)
            device_name = device_info['name'].lower()
            logger.debug(f"Checking device {i}: {device_name}")
            
            if self.device_name in device_name and device_info['maxInputChannels'] > 0:
                logger.info(f"Found matching device: {device_info['name']} (index {i})")
                return i
        
        logger.warning("Suitable input device not found")
        return None
    
    def setup_audio_stream(self):
        """Open audio stream"""
        try:
            # Check if this is the ReSpeaker device with 2 channels (AEC support)
            device_info = self.p.get_device_info_by_index(self.input_device_index)
            max_channels = device_info.get('maxInputChannels', 1)
            device_name_lower = device_info['name'].lower()
            
            # ONLY support reachy devices with 2 channels
            # ReSpeaker XVF3800 has 2 channels:
            # Channel 0: AEC-processed microphone (echo-cancelled)
            # Channel 1: Reference/playback signal
            # We need to record both channels but will use only channel 0
            if 'reachy' not in device_name_lower:
                error_msg = (
                    f"Unsupported audio device: '{device_info['name']}'. "
                    f"Only 'reachy' devices are supported. "
                    f"Please use --device reachy or set AUDIO_DEVICE_NAME=reachy"
                )
                logger.error(error_msg)
                raise RuntimeError(error_msg)
            
            if max_channels < 2:
                error_msg = (
                    f"Device '{device_info['name']}' has {max_channels} channel(s), but 2 channels are required. "
                    f"Please ensure you're using a ReSpeaker XVF3800 device with 2-channel AEC support."
                )
                logger.error(error_msg)
                raise RuntimeError(error_msg)
            
            # Valid reachy device with 2 channels
            self.num_channels = 2
            self.use_aec_channel = True
            logger.info(f"Using reachy device '{device_info['name']}' with 2-channel AEC mode (will use channel 0 for echo cancellation)")
            
            self.stream = self.p.open(
                format=pyaudio.paInt16,
                channels=self.num_channels,
                rate=self.rate,
                input=True,
                frames_per_buffer=self.chunk_size,
                input_device_index=self.input_device_index
            )
            logger.info(f"Audio stream opened successfully with {self.num_channels} channel(s)")
        except IOError as e:
            logger.error(f"Error opening audio stream: {e}")
            raise
    
    async def accept_clients(self):
        """Accept new client connections"""
        while True:
            try:
                # Try to accept new connections (non-blocking)
                try:
                    client_socket, _ = self.server_socket.accept()
                    client_socket.setblocking(False)
                    self.clients.append(client_socket)
                    logger.info(f"New client connected. Total clients: {len(self.clients)}")
                except BlockingIOError:
                    pass
                
                await asyncio.sleep(0.1)
            except Exception as e:
                logger.error(f"Error accepting clients: {e}")
                await asyncio.sleep(1)
    
    async def emit_event(self, event_type, data=None):
        """Emit event to all connected clients asynchronously"""
        event = {
            "type": event_type,
            "timestamp": datetime.utcnow().isoformat(),
            "data": data or {}
        }
        
        message = json.dumps(event) + "\n"
        message_bytes = message.encode('utf-8')
        
        # Send to all clients
        disconnected_clients = []
        for client in self.clients:
            try:
                # Run the blocking sendall in a thread to avoid blocking the event loop
                await asyncio.to_thread(client.sendall, message_bytes)
            except (BrokenPipeError, ConnectionResetError) as e:
                logger.warning(f"Client disconnected: {e}")
                disconnected_clients.append(client)
            except Exception as e:
                logger.error(f"Error sending to client: {e}")
                disconnected_clients.append(client)
        
        # Remove disconnected clients
        for client in disconnected_clients:
            try:
                client.close()
            except:
                pass
            self.clients.remove(client)
        
        if disconnected_clients:
            logger.info(f"Removed {len(disconnected_clients)} disconnected clients. Active: {len(self.clients)}")
        
        logger.debug(f"Emitted event: {event_type}")
    
    def is_speech(self, data):
        """Check if audio data contains speech using VAD"""
        return self.vad.is_speech(data)
    
    async def log_speech_event(self, event_type, duration=None, transcription=None):
        """Log and emit speech detection events"""
        current_time = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime())
        
        if event_type == "start":
            self.speech_events += 1
            message = f"Speech started (Event #{self.speech_events})"
            logger.info(f"[{current_time}] {message} {transcription}")
            
            await self.emit_event("speech_started", {
                "event_number": self.speech_events,
                "timestamp": current_time
            })
            
        elif event_type == "stop":
            message = f"Speech stopped (Event #{self.speech_events})"
            if duration:
                message += f" - Duration: {duration:.2f} seconds"
            if transcription:
                message += f" - Transcription: '{transcription}'"
            
            logger.info(f"[{current_time}] {message}")
            
            await self.emit_event("speech_stopped", {
                "event_number": self.speech_events,
                "duration": duration,
                "transcription": transcription,
                "timestamp": current_time
            })
    
    async def listen(self):
        """Continuously listen to audio and buffer it"""
        while True:
            try:
                data = await asyncio.to_thread(
                    self.stream.read,
                    self.chunk_size,
                    exception_on_overflow=False
                )
                np_data = np.frombuffer(data, dtype=np.int16)
                
                # If using 2-channel ReSpeaker, extract only channel 0 (AEC-processed)
                if self.use_aec_channel and self.num_channels == 2:
                    # Reshape to (frames, channels) and take only channel 0
                    np_data = np_data.reshape(-1, 2)[:, 0]
                
                async with self.processing_lock:
                    self.audio_buffer.append(np_data)
                    
            except Exception as e:
                logger.error(f"Error during audio capture: {e}", exc_info=True)
                await asyncio.sleep(0.1)
    
    async def process(self):
        """Process buffered audio and detect speech"""
        while True:
            # Get data from buffer with minimal lock time
            data = None
            async with self.processing_lock:
                if len(self.audio_buffer) > 0:
                    data = self.audio_buffer.popleft()
            
            # Process data outside the lock
            if data is not None:
                # Run CPU-bound VAD check in a thread to avoid blocking the event loop
                is_speech = await asyncio.to_thread(self.is_speech, data.tobytes())
                
                # Handle state (no lock needed here)
                if is_speech:
                    await self.handle_speech(data)
                else:
                    # If collecting post-speech, still add to buffer
                    if self.collecting_post_speech:
                        self.post_speech_buffer.append(data)
                    await self.handle_silence()
            else:
                # No data, sleep briefly
                await asyncio.sleep(0.01)
    
    async def handle_speech(self, data):
        """Handle detected speech"""
        if not self.speech_detected and not self.collecting_post_speech:
            self.start_time = time.time()
            self.last_partial_transcription_time = time.time()
            #await self.log_speech_event("start")
            self.speech_detected = True
            self.speech_buffer = []
            self.post_speech_buffer = []
            self.last_partial_text = ""
            logger.debug("Speech detected, starting new buffer")
        
        if self.speech_detected:
            await self.log_speech_event("ongoing")

            self.speech_buffer.append(data)
            self.silence_start_time = None  # Reset silence timer
            
            # Check if we should perform partial transcription
            if self.enable_partial_transcription and not self.partial_transcription_in_progress:
                current_time = time.time()
                time_since_last_partial = current_time - self.last_partial_transcription_time
                
                if (time_since_last_partial >= self.partial_transcription_interval and 
                    len(self.speech_buffer) >= self.min_partial_chunks):
                    # Trigger partial transcription in background
                    asyncio.create_task(self.process_partial_speech())
                    
        elif self.collecting_post_speech:
            # Add to post-speech buffer
            self.post_speech_buffer.append(data)
            # If we detect speech again during post-speech collection, restart speech detection
            self.speech_detected = True
            self.collecting_post_speech = False
            self.silence_start_time = None
            logger.debug("Speech resumed during post-speech collection, continuing speech detection")
    
    async def handle_silence(self):
        """Handle silence (potential end of speech)"""
        if self.speech_detected:
            if self.silence_start_time is None:
                self.silence_start_time = time.time()
                logger.info("Silence detected, starting silence timer")
            elif time.time() - self.silence_start_time >= self.min_silence_duration:
                logger.info("Silence duration exceeded, starting post-speech collection")
                # Start collecting post-speech audio
                self.speech_detected = False
                self.collecting_post_speech = True
                self.post_speech_start_time = time.time()
        elif self.collecting_post_speech:
            # Continue collecting post-speech audio for buffer duration
            if time.time() - self.post_speech_start_time >= self.post_speech_buffer_duration:
                logger.info("Post-speech buffer complete, processing speech")
                await self.process_speech()
                self.collecting_post_speech = False
    
    async def process_partial_speech(self):
        """Process partial speech chunk for real-time word detection"""
        if self.partial_transcription_in_progress:
            return
        
        self.partial_transcription_in_progress = True
        
        try:
            # Take a snapshot of the current speech buffer
            current_chunks = self.speech_buffer.copy()
            
            if not current_chunks or len(current_chunks) < self.min_partial_chunks:
                return
            
            logger.info(f"Processing partial transcription with {len(current_chunks)} chunks")
            
            # Perform partial STT transcription
            partial_transcription = None
            try:
                partial_transcription = await self.transcribe_audio(current_chunks)
                
                if partial_transcription and any(c.isalnum() for c in partial_transcription):
                    logger.info(f"Partial transcription: '{partial_transcription}'")
                    
                    # Only emit if the text has changed significantly
                    if partial_transcription != self.last_partial_text:
                        self.last_partial_text = partial_transcription
                        
                        # Emit partial transcription event
                        await self.emit_event("speech_partial", {
                            "event_number": self.speech_events,
                            "partial_text": partial_transcription,
                            "duration_so_far": time.time() - self.start_time,
                            "is_partial": True,
                            "timestamp": time.strftime("%Y-%m-%d %H:%M:%S", time.localtime())
                        })
                else:
                    logger.debug("Partial transcription returned no valid text")
                    
            except Exception as e:
                logger.error(f"Error during partial transcription: {e}", exc_info=True)
            
            # Update the last partial transcription time
            self.last_partial_transcription_time = time.time()
            
        finally:
            self.partial_transcription_in_progress = False
    
    async def process_speech(self):
        """Process completed speech segment with STT transcription"""
        duration = time.time() - self.start_time
        
        # Combine speech buffer with post-speech buffer
        all_audio_chunks = self.speech_buffer + self.post_speech_buffer
        audio_size = len(all_audio_chunks) * self.chunk_size * 2  # 2 bytes per sample
        
        logger.info(f"Processing speech segment: {len(self.speech_buffer)} speech chunks + {len(self.post_speech_buffer)} post-speech chunks = {len(all_audio_chunks)} total chunks, {audio_size} bytes")
        
        # Perform STT transcription
        transcription = None
        if all_audio_chunks:
            try:
                transcription = await self.transcribe_audio(all_audio_chunks)
                logger.info(f"Transcription result: '{transcription}'")
            except Exception as e:
                logger.error(f"Error during transcription: {e}", exc_info=True)
        # contains characters
        if transcription and any(c.isalnum() for c in transcription):
            # Emit completion event with transcription
            await self.log_speech_event("stop", duration, transcription)
            
            # Optional: Save audio file for debugging
            if os.getenv('SAVE_AUDIO_FILES', 'false').lower() == 'true':
                await self.save_audio_file(all_audio_chunks)
        else:
            logger.info("No valid transcription obtained")
            logger.info("Emitting speech stopped event without transcription")
        # Reset state
        self.speech_detected = False
        self.silence_start_time = None
        self.speech_buffer = []
        self.post_speech_buffer = []
        self.last_partial_text = ""
        self.partial_transcription_in_progress = False
    
    async def transcribe_audio(self, audio_chunks):
        """Transcribe audio using faster-whisper"""
        if not audio_chunks:
            return None
        
        try:
            logger.info(f"Starting transcription of {len(audio_chunks)} chunks")
            
            # Use the WhisperSTT module
            transcription = await asyncio.to_thread(
                self.whisper.transcribe_audio_data,
                audio_chunks,
                self.rate,
                2  # sample_width for int16
            )
            
            if transcription:
                logger.info(f"Transcription result: '{transcription}'")
            
            return transcription
            
        except Exception as e:
            logger.error(f"Error in transcribe_audio: {e}", exc_info=True)
            return None
    
    async def save_audio_file(self, audio_chunks):
        """Save recorded speech to file"""
        if not audio_chunks:
            return
        
        try:
            combined_audio = np.concatenate(audio_chunks)
            filename = f"speech_{self.speech_events}_{int(time.time())}.wav"
            
            # Use WhisperSTT's save method
            await asyncio.to_thread(
                self.whisper._save_audio_to_wav,
                combined_audio,
                filename,
                self.rate
            )
            logger.info(f"Saved audio to {filename}")
        except Exception as e:
            logger.error(f"Error saving audio file: {e}")
    
    async def run(self):
        """Main run loop"""
        logger.info("Starting Hearing Event Emitter service")
        logger.info(f"Device: {self.device_name}")
        logger.info(f"Rate: {self.rate} Hz")
        logger.info(f"Socket: {self.socket_path}")
        
        # Initialize audio device
        self.initialize_input_device()
        self.setup_audio_stream()
        
        # Start tasks
        accept_task = asyncio.create_task(self.accept_clients())
        listen_task = asyncio.create_task(self.listen())
        process_task = asyncio.create_task(self.process())
        
        try:
            await asyncio.gather(accept_task, listen_task, process_task)
        except Exception as e:
            logger.error(f"Error during service operation: {e}", exc_info=True)
        finally:
            self.cleanup()
    
    def cleanup(self):
        """Clean up resources"""
        logger.info("Cleaning up resources")
        
        # Close audio stream
        if self.stream:
            try:
                self.stream.stop_stream()
                self.stream.close()
            except:
                pass
        
        # Terminate PyAudio
        if self.p:
            try:
                self.p.terminate()
            except:
                pass
        
        # Close all client connections
        for client in self.clients:
            try:
                client.close()
            except:
                pass
        
        # Close server socket
        if self.server_socket:
            try:
                self.server_socket.close()
            except:
                pass
        
        # Remove socket file
        if os.path.exists(self.socket_path):
            try:
                os.remove(self.socket_path)
            except:
                pass
        
        logger.info("Cleanup complete")


def main():
    """Main entry point"""
    parser = argparse.ArgumentParser(
        description='Hearing Event Emitter - VAD-based speech detection service'
    )
    parser.add_argument(
        '--device',
        type=str,
        default=None,
        help='Audio device name (e.g., ReSpeaker, default)'
    )
    parser.add_argument(
        '--language',
        type=str,
        default='en',
        help='Language code for future use (default: en)'
    )
    
    args = parser.parse_args()
    
    emitter = HearingEventEmitter(device_name=args.device, language=args.language)
    
    try:
        asyncio.run(emitter.run())
    except KeyboardInterrupt:
        logger.info("Keyboard interrupt received, terminating...")
    except Exception as e:
        logger.error(f"Unexpected error: {e}", exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    main()
