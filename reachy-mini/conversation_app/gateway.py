#!/usr/bin/env python3
"""
Reachy Gateway - Unified service for daemon management, hearing, and vision event emission

This service:
1. Manages the reachy-mini-daemon lifecycle (spawn and cleanup)
2. Runs hearing logic (VAD, STT, DOA)
3. Runs vision logic (video frame capture and processing)
4. Emits events via Unix Domain Socket
5. Handles graceful shutdown via signals
6. Continuously records audio and saves to WAV files
7. Continuously captures video frames and saves to image files
8. Points robot head at speaker based on DOA

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
from reachy_mini.utils.interpolation import InterpolationTechnique

# Import our custom modules
from .gateway_audio import GatewayAudio
#from .gateway_video import GatewayVideo

from .reachy_controller import ReachyController

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
    
    def __init__(self, device_name=None, language='en', event_callback=None, enable_socket_server=True):
        logger.info("Initializing Reachy Gateway")
        
        # Store callback and socket server flag
        self.event_callback = event_callback
        self.enable_socket_server = enable_socket_server
        
        # Configuration from environment or defaults
        self.device_name = (device_name or os.getenv('AUDIO_DEVICE_NAME', 'default')).lower()
        self.language = language
        self.socket_path = os.getenv('SOCKET_PATH', '/tmp/reachy_sockets/hearing.sock')
        
        # DOA detector initialization (this will spawn the daemon)
        logger.info("Initializing DOA detector (this will spawn the daemon)...")
        try:
            self.reachy_controller = ReachyController(smoothing_alpha=0.1, log_level=logging.INFO)
            logger.info("✅ Reachy Mini daemon spawned successfully")
        except Exception as e:
            logger.error(f"Failed to initialize DOA detector (daemon spawn failed): {e}", exc_info=True)
            self.reachy_controller = None
            raise
        
        # Initialize audio processing component
        logger.info("Initializing audio processing component...")
        self.gateway_audio = GatewayAudio(
            reachy_controller=self.reachy_controller,
            event_callback=self.emit_event,
            language=self.language
        )
        logger.info("✅ Audio processing component initialized")
        
        # Initialize video processing component (conditionally)
        self.gateway_video = None
        enable_vision = os.getenv('ENABLE_VISION', 'true').lower() in ('true', '1', 'yes')
        
        if enable_vision:
            try:
                from .gateway_video import GatewayVideo
                logger.info("Initializing video processing component...")
                frame_interval = int(os.getenv('VIDEO_FRAME_INTERVAL', '100'))
                self.gateway_video = GatewayVideo(
                    media=self.reachy_controller.mini.media,
                    event_callback=self.emit_event,
                    frame_interval=frame_interval
                )
                logger.info("✅ Video processing component initialized")
            except ImportError as e:
                logger.warning(f"Video processing disabled - dependencies not available: {e}")
                self.gateway_video = None
        else:
            logger.info("Video processing component: Disabled (ENABLE_VISION=false)")
        
        # Socket setup (conditional)
        self.server_socket = None
        self.clients = []
        if self.enable_socket_server:
            self.setup_socket_server()
        else:
            logger.info("Socket server disabled - using callback mode")
        
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
    
    def move_smoothly_to(self, duration=1.0, roll=None, pitch=None, yaw=None, antennas=None, body_yaw=None):
        """Move the robot smoothly to a target head pose and/or antennas position and/or body direction."""
        self.reachy_controller.move_smoothly_to(duration=duration, roll=roll, pitch=pitch, yaw=yaw, antennas=antennas, body_yaw=body_yaw)
    
    def turn_off_smoothly(self):
        """Smoothly move the robot to a neutral position and then turn off compliance."""
        if self.reachy_controller:
            self.reachy_controller.turn_off_smoothly()

    def get_current_state(self):
        """
        Get current robot state (pose and positions).
        
        Returns:
            Tuple of (roll, pitch, yaw, antennas, body_yaw) all in degrees
        """
        if self.reachy_controller:
            return self.reachy_controller._get_current_state()
        return (0.0, 0.0, 0.0, [0.0, 0.0], 0.0)
    
    def get_current_state_natural(self):
        """
        Get current robot state expressed in natural language (compass directions).
        
        Returns:
            Dictionary with natural language descriptions
        """
        if self.reachy_controller:
            return self.reachy_controller.get_current_state_natural()
        return {
            "head_direction": "North",
            "head_tilt": "level",
            "head_roll": "upright",
            "antennas": "neutral",
            "body_direction": "North"
        }
    
    def _degrees_to_compass(self, degrees: float) -> str:
        """
        Convert compass angle in degrees to nearest cardinal/intercardinal direction.
        
        Args:
            degrees: Compass angle in degrees (0=North, 90=East, -90=West)
        
        Returns:
            Compass direction string (e.g., "North", "North East", "East")
        """
        if self.reachy_controller:
            return self.reachy_controller._degrees_to_compass(degrees)
        return "North"
    
    async def accept_clients(self):
        """Accept new client connections"""
        if not self.enable_socket_server:
            return
        
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
        """Emit event to all connected clients and/or callback asynchronously"""
        event = {
            "type": event_type,
            "timestamp": datetime.utcnow().isoformat(),
            "data": data or {}
        }
        
        # Add DOA information to all events if available
        if self.reachy_controller and hasattr(self, 'gateway_audio') and self.gateway_audio.current_doa is not None:
            doa_dict = self.reachy_controller.get_current_doa_dict()
            if doa_dict:
                event["data"]["doa"] = doa_dict
                logger.debug(f"DOA included in {event_type} event: {doa_dict['angle_degrees']:.1f}° "
                           f"(speech_detected={doa_dict['is_speech_detected']})")
        
        # Call callback if provided
        if self.event_callback:
            try:
                await self.event_callback(event_type, event["data"])
                logger.debug(f"Event callback invoked for: {event_type}")
            except Exception as e:
                logger.error(f"Error in event callback: {e}", exc_info=True)
        
        # Send to socket clients if enabled
        if self.enable_socket_server:
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
            
            logger.debug(f"Emitted event to {len(self.clients)} socket clients: {event_type}")
        
        logger.debug(f"Emitted event: {event_type}")
    
    async def run(self):
        """Main run loop"""
        logger.info("Starting Reachy Gateway service")
        logger.info(f"Device: {self.device_name}")
        logger.info(f"Socket: {self.socket_path}")
        logger.info(f"DOA Detection: {'Enabled' if self.reachy_controller else 'Disabled'}")
        
        if self.gateway_video:
            logger.info(f"Video Capture: Enabled (frame interval: {self.gateway_video.frame_interval})")
        else:
            logger.info("Video Capture: Disabled")
        
        # Set up signal handlers
        self.setup_signal_handlers()
        
        # Start recording via ReachyMini
        logger.info("Starting recording via ReachyMini...")
        self.reachy_controller.start_recording()
        logger.info("✅ Recording started successfully")
        
        # Start tasks
        tasks = []
        
        if self.enable_socket_server:
            accept_task = asyncio.create_task(self.accept_clients())
            tasks.append(accept_task)
        
        # Delegate audio processing to gateway_audio
        listen_task = asyncio.create_task(self.gateway_audio.listen())
        tasks.append(listen_task)
        
        process_task = asyncio.create_task(self.gateway_audio.process())
        tasks.append(process_task)
        
        doa_task = None
        if self.reachy_controller:
            doa_task = asyncio.create_task(self.gateway_audio.sample_doa())
            tasks.append(doa_task)
            logger.info("DOA sampling task started")
        
        # Start video capture (if enabled)
        if self.gateway_video:
            logger.info("Starting video capture...")
            await self.gateway_video.start()
            video_task = asyncio.create_task(self.gateway_video.run_gst_loop())
            tasks.append(video_task)
            logger.info("✅ Video capture task started")
        
        try:
            
            # Run until shutdown is requested
            while not self.shutdown_requested:
                await asyncio.sleep(0.5)
            
            logger.info("Shutdown requested, cancelling tasks...")
            
            # Request shutdown for audio component
            self.gateway_audio.request_shutdown()
            
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
        
        #self.turn_off_smoothly()
        # Stop recording via ReachyMini
        if hasattr(self, 'doa_detector') and self.reachy_controller:
            try:
                self.reachy_controller.stop_recording()
                time.sleep(10)
                logger.info("Recording stopped via ReachyMini")
            except Exception as e:
                logger.error(f"Error stopping recording: {e}")
        
        # Cleanup video capture (if enabled)
        if hasattr(self, 'gateway_video') and self.gateway_video:
            try:
                self.gateway_video.cleanup()
                logger.info("Video capture cleaned up")
            except Exception as e:
                logger.error(f"Error cleaning up video capture: {e}")
        
        # Cleanup DOA detector (this will also stop the daemon)
        if self.reachy_controller:
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
