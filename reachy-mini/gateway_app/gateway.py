#!/usr/bin/env python3
"""
Reachy Gateway - Unified service for daemon management and hearing event emission

This service:
1. Manages the reachy-mini-daemon lifecycle (spawn and cleanup)
2. Runs hearing logic (VAD, STT, DOA)
3. Emits events via Unix Domain Socket
4. Handles graceful shutdown via signals
5. Continuously records audio and saves to WAV files
6. Points robot head at speaker based on DOA

Usage:
    python3 gateway.py --device Reachy --language en
"""

import time
import numpy as np
import os
import socket
import sys
import logging
import json
import argparse
import signal
from datetime import datetime
from dotenv import load_dotenv
import asyncio
from collections import deque
from pathlib import Path
import torch
import soundfile as sf

# Import our custom modules
from vad_detector import VADDetector
from whisper_stt import WhisperSTT
from reachy_controller import ReachyController

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)
logger.info("Reachy Gateway starting...")

# Load environment variables
load_dotenv()
logger.debug("Environment variables loaded")


class ReachyGateway:
    """Unified gateway service for daemon management and hearing event emission"""
    
    def __init__(self, device_name=None, language='en'):
        logger.info("Initializing Reachy Gateway")
        
        # Configuration from environment or defaults
        self.device_name = (device_name or os.getenv('AUDIO_DEVICE_NAME', 'default')).lower()
        self.language = language
        self.socket_path = os.getenv('SOCKET_PATH', '/tmp/reachy_sockets/hearing.sock')
        
        # Audio configuration
        self.rate = int(os.getenv('SAMPLE_RATE', '16000'))
        self.chunk_duration_ms = int(os.getenv('CHUNK_DURATION_MS', '30'))
        self.chunk_size = int(self.rate * self.chunk_duration_ms / 1000)
        
        # VAD configuration - DISABLED, using DOA speech detection instead
        self.use_vad = os.getenv('USE_VAD', 'false').lower() == 'true'
        if self.use_vad:
            vad_aggressiveness = int(os.getenv('VAD_AGGRESSIVENESS', '3'))
            self.vad = VADDetector(aggressiveness=vad_aggressiveness, sample_rate=self.rate)
            logger.info("Using VAD for speech detection")
        else:
            self.vad = None
            logger.info("VAD disabled - will use DOA speech detection")
        
        # Speech detection configuration
        self.min_silence_duration = float(os.getenv('MIN_SILENCE_DURATION', '0.5'))
        self.post_speech_buffer_duration = float(os.getenv('POST_SPEECH_BUFFER_DURATION', '0.5'))
        self.lower_threshold = int(os.getenv('SPEECH_THRESHOLD_LOWER', '1500'))
        self.upper_threshold = int(os.getenv('SPEECH_THRESHOLD_UPPER', '2500'))
        self.min_audio_bytes = 4000
        
        # Partial transcription configuration
        self.enable_partial_transcription = os.getenv('ENABLE_PARTIAL_TRANSCRIPTION', 'true').lower() == 'true'
        self.partial_transcription_interval = float(os.getenv('PARTIAL_TRANSCRIPTION_INTERVAL', '1.0'))
        self.min_partial_chunks = int(os.getenv('MIN_PARTIAL_CHUNKS', '10'))
        
        # Buffers
        buffer_size = int(os.getenv('AUDIO_BUFFER_SIZE', '100'))
        self.audio_buffer = deque(maxlen=buffer_size)
        self.speech_buffer = []
        self.post_speech_buffer = []
        
        # Recording state for continuous audio collection
        self.recording_samples = []
        self.recording_duration = float(os.getenv('RECORDING_DURATION', '5.0'))  # seconds
        self.recording_start_time = None
        self.recordings_dir = os.getenv('RECORDINGS_DIR', './recordings')
        os.makedirs(self.recordings_dir, exist_ok=True)
        
        # DOA head-pointing state
        self.last_doa = -1
        self.doa_threshold = float(os.getenv('DOA_THRESHOLD', '0.004'))  # ~2 degrees
        
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
        
        # DOA detector initialization (this will spawn the daemon)
        logger.info("Initializing DOA detector (this will spawn the daemon)...")
        try:
            self.reachy_controller = ReachyController(smoothing_alpha=0.1, log_level=logging.ERROR)
            self.current_doa = None
            self.doa_sample_interval = float(os.getenv('DOA_SAMPLE_INTERVAL', '0.1'))
            self.last_doa_sample_time = None
            logger.info(f"DOA detector initialized with sample interval: {self.doa_sample_interval}s")
            logger.info("✅ Reachy Mini daemon spawned successfully")
        except Exception as e:
            logger.error(f"Failed to initialize DOA detector (daemon spawn failed): {e}", exc_info=True)
            self.reachy_controller = None
            raise
        
        # Socket setup
        self.server_socket = None
        self.clients = []
        self.setup_socket_server()
        
        # Shutdown flag
        self.shutdown_requested = False
        
        logger.info("Reachy Gateway initialization complete")
    
    def setup_signal_handlers(self):
        """Register signal handlers for graceful shutdown"""
        def signal_handler(signum, frame):
            sig_name = signal.Signals(signum).name
            logger.info(f"Received signal {sig_name} ({signum}), initiating graceful shutdown...")
            self.shutdown_requested = True
        
        signal.signal(signal.SIGTERM, signal_handler)
        signal.signal(signal.SIGINT, signal_handler)
        logger.info("Signal handlers registered for SIGTERM and SIGINT")
    
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
    

    
    async def accept_clients(self):
        """Accept new client connections"""
        while not self.shutdown_requested:
            try:
                try:
                    client_socket, _ = self.server_socket.accept()
                    client_socket.setblocking(False)
                    self.clients.append(client_socket)
                    logger.info(f"New client connected. Total clients: {len(self.clients)}")
                except BlockingIOError:
                    pass
                
                await asyncio.sleep(0.1)
            except Exception as e:
                if not self.shutdown_requested:
                    logger.error(f"Error accepting clients: {e}")
                await asyncio.sleep(1)
    
    async def emit_event(self, event_type, data=None):
        """Emit event to all connected clients asynchronously"""
        event = {
            "type": event_type,
            "timestamp": datetime.utcnow().isoformat(),
            "data": data or {}
        }
        
        # Add DOA information to all events if available
        if self.reachy_controller and self.current_doa is not None:
            doa_dict = self.reachy_controller.get_current_doa_dict()
            if doa_dict:
                event["data"]["doa"] = doa_dict
                logger.debug(f"DOA included in {event_type} event: {doa_dict['angle_degrees']:.1f}° "
                           f"(speech_detected={doa_dict['is_speech_detected']})")
        
        message = json.dumps(event) + "\n"
        message_bytes = message.encode('utf-8')
        
        # Send to all clients
        disconnected_clients = []
        for client in self.clients:
            try:
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
        logger.debug(f"Emitted event: {message.strip()}")
    
    def is_speech(self, data):
        """Check if audio data contains speech using VAD or DOA"""
        if self.use_vad and self.vad:
            return self.vad.is_speech(data)
        else:
            # Use DOA speech detection instead
            if self.current_doa is not None:
                return self.current_doa[1]  # is_speech_detected flag from DOA
            return False
    
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
        """Continuously listen to audio and collect samples for recording"""
        logger.info("Starting listen loop for audio collection and recording")
        
        # Initialize recording
        self.recording_start_time = time.time()
        self.recording_samples = []
        
        while not self.shutdown_requested:
            try:
                # Get audio sample from ReachyMini via ReachyController
                sample = await asyncio.to_thread(self.reachy_controller.get_audio_sample)
                
                if sample is None:
                    # No sample available yet, wait a bit
                    await asyncio.sleep(0.01)
                    continue
                
                # Verify we received mono audio (1D array)
                if len(sample.shape) != 1:
                    logger.error(f"Expected mono audio (1D array), got shape: {sample.shape}")
                    continue
                
                # ReachyMini may return float arrays, convert to int16 if needed
                if sample.dtype == np.float32 or sample.dtype == np.float64:
                    # Normalize and convert to int16
                    np_data = (sample * 32767).astype(np.int16)
                    logger.debug(f"Converted float audio sample to int16, shape: {np_data.shape}")
                elif sample.dtype == np.int16:
                    np_data = sample
                else:
                    logger.warning(f"Unexpected audio data type: {sample.dtype}, attempting conversion")
                    np_data = sample.astype(np.int16)
                
                # Add to buffers
                async with self.processing_lock:
                    self.audio_buffer.append(np_data)
                    self.recording_samples.append(np_data)
                
                # === Periodic Recording Save ===
                # Check if we should save the recording
                elapsed_time = time.time() - self.recording_start_time
                if elapsed_time >= self.recording_duration:
                    logger.info(f"Recording duration ({self.recording_duration}s) reached, saving...")
                    await self.save_recording()
                    # Reset recording
                    self.recording_samples = []
                    self.recording_start_time = time.time()
                    
            except Exception as e:
                if not self.shutdown_requested:
                    logger.error(f"Error during audio capture: {e}", exc_info=True)
                await asyncio.sleep(0.1)
    
    async def process(self):
        """Process buffered audio and detect speech"""
        while not self.shutdown_requested:
            data = None
            async with self.processing_lock:
                if len(self.audio_buffer) > 0:
                    data = self.audio_buffer.popleft()
            
            if data is not None:
                # Use thread for VAD only, DOA is already async
                if self.use_vad and self.vad:
                    is_speech = await asyncio.to_thread(self.is_speech, data.tobytes())
                else:
                    # DOA-based detection, no need for thread
                    is_speech = self.is_speech(data.tobytes())
                
                if is_speech:
                    await self.handle_speech(data)
                else:
                    if self.collecting_post_speech:
                        self.post_speech_buffer.append(data)
                    await self.handle_silence()
            else:
                await asyncio.sleep(0.01)
    
    async def handle_speech(self, data):
        """Handle detected speech"""
        if not self.speech_detected and not self.collecting_post_speech:
            self.start_time = time.time()
            self.last_partial_transcription_time = time.time()
            self.speech_detected = True
            self.speech_buffer = []
            self.post_speech_buffer = []
            self.last_partial_text = ""
            
            # Clear DOA buffer for new speech segment
            if self.reachy_controller:
                self.reachy_controller.start_speech_segment()
                logger.info("Speech detected, starting new buffer and clearing DOA buffer")
            else:
                logger.debug("Speech detected, starting new buffer")
        
        if self.speech_detected:
            # Emit ongoing event with current DOA
            await self.emit_event("speech_ongoing", {
                "event_number": self.speech_events,
                "duration_so_far": time.time() - self.start_time
            })

            self.speech_buffer.append(data)
            self.silence_start_time = None
            
            # Check if we should perform partial transcription
            if self.enable_partial_transcription and not self.partial_transcription_in_progress:
                current_time = time.time()
                time_since_last_partial = current_time - self.last_partial_transcription_time
                
                if (time_since_last_partial >= self.partial_transcription_interval and 
                    len(self.speech_buffer) >= self.min_partial_chunks):
                    asyncio.create_task(self.process_partial_speech())
                    
        elif self.collecting_post_speech:
            self.post_speech_buffer.append(data)
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
                self.speech_detected = False
                self.collecting_post_speech = True
                self.post_speech_start_time = time.time()
        elif self.collecting_post_speech:
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
            current_chunks = self.speech_buffer.copy()
            
            if not current_chunks or len(current_chunks) < self.min_partial_chunks:
                return
            
            logger.info(f"Processing partial transcription with {len(current_chunks)} chunks")
            
            partial_transcription = None
            try:
                partial_transcription = await self.transcribe_audio(current_chunks)
                
                if partial_transcription and any(c.isalnum() for c in partial_transcription):
                    logger.info(f"Partial transcription: '{partial_transcription}'")
                    
                    if partial_transcription != self.last_partial_text:
                        self.last_partial_text = partial_transcription
                        
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
            
            self.last_partial_transcription_time = time.time()
            
        finally:
            self.partial_transcription_in_progress = False
    
    async def process_speech(self):
        """Process completed speech segment with STT transcription"""
        duration = time.time() - self.start_time
        
        all_audio_chunks = self.speech_buffer + self.post_speech_buffer
        audio_size = len(all_audio_chunks) * self.chunk_size * 2
        
        logger.info(f"Processing speech segment: {len(self.speech_buffer)} speech chunks + {len(self.post_speech_buffer)} post-speech chunks = {len(all_audio_chunks)} total chunks, {audio_size} bytes")
        
        # Get average DOA for this speech segment
        avg_doa = None
        if self.reachy_controller:
            avg_doa = self.reachy_controller.get_average_doa()
            if avg_doa:
                logger.info(f"Average DOA over speech segment: {avg_doa['angle_degrees']:.1f}° "
                           f"from {avg_doa['sample_count']} samples")
            else:
                logger.info("No DOA samples collected during speech segment")
        
        # Perform STT transcription
        transcription = None
        if all_audio_chunks:
            try:
                transcription = await self.transcribe_audio(all_audio_chunks)
                logger.info(f"Transcription result: '{transcription}'")
            except Exception as e:
                logger.error(f"Error during transcription: {e}", exc_info=True)
        
        if transcription and any(c.isalnum() for c in transcription):
            event_data = {
                "event_number": self.speech_events,
                "duration": duration,
                "transcription": transcription,
                "timestamp": time.strftime("%Y-%m-%d %H:%M:%S", time.localtime())
            }
            
            if avg_doa:
                event_data["doa_average"] = avg_doa
                logger.info(f"DOA average saved to speech_stopped event")
            
            await self.emit_event("speech_stopped", event_data)
            logger.info(f"[{event_data['timestamp']}] Speech stopped (Event #{self.speech_events}) - "
                       f"Duration: {duration:.2f} seconds - Transcription: '{transcription}'")
            
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
            
            transcription = await asyncio.to_thread(
                self.whisper.transcribe_audio_data,
                audio_chunks,
                self.rate,
                2
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
            
            await asyncio.to_thread(
                self.whisper._save_audio_to_wav,
                combined_audio,
                filename,
                self.rate
            )
            logger.info(f"Saved audio to {filename}")
        except Exception as e:
            logger.error(f"Error saving audio file: {e}")
    
    async def save_recording(self):
        """Save collected audio samples to a WAV file"""
        if not self.recording_samples:
            logger.warning("No audio data to save")
            return
        
        try:
            # Concatenate all samples
            audio_data = np.concatenate(self.recording_samples, axis=0)
            
            # Generate filename with timestamp
            timestamp = int(time.time())
            filename = os.path.join(self.recordings_dir, f"recorded_audio_{timestamp}.wav")
            
            # Get sample rate
            sample_rate = await asyncio.to_thread(self.reachy_controller.get_sample_rate)
            
            # Save to WAV file
            await asyncio.to_thread(
                sf.write,
                filename,
                audio_data,
                sample_rate
            )
            
            logger.info(f"Audio saved to {filename} ({len(audio_data)} samples, {len(audio_data)/sample_rate:.2f}s)")
            
        except Exception as e:
            logger.error(f"Error saving recording: {e}", exc_info=True)
    
    async def sample_doa(self):
        """Continuously sample DOA from ReachyMini and point head at speaker"""
        if not self.reachy_controller:
            logger.warning("DOA detector not available, skipping DOA sampling")
            return
        
        while not self.shutdown_requested:
            try:
                # Sample DOA
                doa = await asyncio.to_thread(self.reachy_controller.get_current_doa)
                self.current_doa = doa
                logger.debug(f"DOA sampled: angle={doa[0]:.3f} rad ({np.degrees(doa[0]):.1f}°), "
                           f"speech_detected={doa[1]}")
                
                # Head-pointing logic: point at speaker when DOA changes significantly
                if doa[1] and np.abs(doa[0] - self.last_doa) > self.doa_threshold:
                    # Speech detected and significant DOA change
                    logger.info(f"Speech detected at {doa[0]:.1f} radians ({np.degrees(doa[0]):.1f}°)")
                    
                    # Calculate head pointing vector
                    p_head = [np.sin(doa[0]), np.cos(doa[0]), 0.0]
                    logger.info(f"Pointing to x={p_head[0]:.2f}, y={p_head[1]:.2f}, z={p_head[2]:.2f}")
                    
                    # Transform to world coordinates
                    T_world_head = await asyncio.to_thread(self.reachy_controller.mini.get_current_head_pose)
                    R_world_head = T_world_head[:3, :3]
                    p_world = R_world_head @ p_head
                    logger.info(f"In world coordinates: x={p_world[0]:.2f}, y={p_world[1]:.2f}, z={p_world[2]:.2f}")
                    
                    # # Point head at speaker
                    # await asyncio.to_thread(
                    #     self.reachy_controller.mini.look_at_world,
                    #     p_world[0], p_world[1], p_world[2],
                    #     duration=0.5
                    # )
                    # logger.info("Head pointed at speaker")
                    
                    self.last_doa = doa[0]
                else:
                    if not doa[1]:
                        logger.debug("No speech detected")
                    else:
                        logger.debug(f"Small change in DOA: {doa[0]:.1f}° (last was {self.last_doa:.1f}°). Not moving.")
                
                # Buffer DOA samples during speech for averaging
                if self.speech_detected and doa[1]:
                    self.reachy_controller.add_doa_sample(doa)
                    logger.debug(f"DOA sample buffered for averaging")
                
                await asyncio.sleep(self.doa_sample_interval)
            except Exception as e:
                if not self.shutdown_requested:
                    logger.error(f"Error sampling DOA: {e}", exc_info=True)
                await asyncio.sleep(1)
    
    async def run(self):
        """Main run loop"""
        logger.info("Starting Reachy Gateway service")
        logger.info(f"Device: {self.device_name}")
        logger.info(f"Rate: {self.rate} Hz")
        logger.info(f"Socket: {self.socket_path}")
        logger.info(f"DOA Detection: {'Enabled' if self.reachy_controller else 'Disabled'}")
        
        # Set up signal handlers
        self.setup_signal_handlers()
        
        # Start recording via ReachyMini
        logger.info("Starting recording via ReachyMini...")
        self.reachy_controller.start_recording()
        logger.info("✅ Recording started successfully")
        
        # Start tasks
        accept_task = asyncio.create_task(self.accept_clients())
        listen_task = asyncio.create_task(self.listen())
        process_task = asyncio.create_task(self.process())
        
        doa_task = None
        if self.reachy_controller:
            doa_task = asyncio.create_task(self.sample_doa())
            logger.info("DOA sampling task started")
        
        try:
            tasks = [accept_task, listen_task, process_task]
            if doa_task:
                tasks.append(doa_task)
            
            # Run until shutdown is requested
            while not self.shutdown_requested:
                await asyncio.sleep(0.5)
            
            logger.info("Shutdown requested, cancelling tasks...")
            for task in tasks:
                task.cancel()
            
            # Wait for tasks to complete
            await asyncio.gather(*tasks, return_exceptions=True)
            
        except Exception as e:
            logger.error(f"Error during service operation: {e}", exc_info=True)
        finally:
            self.cleanup()
    
    def cleanup(self):
        """Clean up resources"""
        logger.info("Cleaning up resources")
        
        # Stop recording via ReachyMini
        if hasattr(self, 'doa_detector') and self.reachy_controller:
            try:
                self.reachy_controller.stop_recording()
                logger.info("Recording stopped via ReachyMini")
            except Exception as e:
                logger.error(f"Error stopping recording: {e}")
        
        # Cleanup DOA detector (this will also stop the daemon)
        if hasattr(self, 'doa_detector') and self.reachy_controller:
            try:
                self.reachy_controller.cleanup()
                logger.info("DOA detector cleaned up (daemon stopped)")
            except Exception as e:
                logger.error(f"Error cleaning up DOA detector: {e}")
        
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
        description='Reachy Gateway - Unified daemon and hearing service'
    )
    parser.add_argument(
        '--device',
        type=str,
        default=None,
        help='Audio device name (e.g., Reachy, default)'
    )
    parser.add_argument(
        '--language',
        type=str,
        default='en',
        help='Language code for transcription (default: en)'
    )
    
    args = parser.parse_args()
    
    gateway = ReachyGateway(device_name=args.device, language=args.language)
    
    try:
        asyncio.run(gateway.run())
    except KeyboardInterrupt:
        logger.info("Keyboard interrupt received, terminating...")
    except Exception as e:
        logger.error(f"Unexpected error: {e}", exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    main()
