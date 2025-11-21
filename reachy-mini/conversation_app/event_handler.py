#!/usr/bin/env python3
"""
Event Handler Module for Conversation Application

This module handles speech events from the hearing_event_emitter service,
managing socket connections and event processing.

Key features:
1. Unix Domain Socket connection management
2. Event listening and parsing
3. Speech started/stopped event handling
4. Event-driven conversation flow
"""

import asyncio
import json
import socket
import os
import logging
from typing import Dict, Any, Callable, Optional, Awaitable

logger = logging.getLogger(__name__)


class EventHandler:
    """Handles speech events from the hearing service via Unix Domain Socket."""
    
    def __init__(self, socket_path: str = None):
        """
        Initialize the event handler.
        
        Args:
            socket_path: Path to the Unix Domain Socket (default: from SOCKET_PATH env var)
        """
        self.socket_path = socket_path or os.getenv('SOCKET_PATH', '/tmp/reachy_sockets/hearing.sock')
        self.socket: Optional[socket.socket] = None
        self.socket_buffer = ""
        
        # State tracking
        self.is_speaking = False
        self.current_speech_event: Optional[Dict[str, Any]] = None
        self.processing_speech = False
        
        # Event callbacks
        self.on_speech_started_callback: Optional[Callable[[Dict[str, Any]], Awaitable[None]]] = None
        self.on_speech_stopped_callback: Optional[Callable[[Dict[str, Any]], Awaitable[None]]] = None
    
    def set_speech_started_callback(self, callback: Callable[[Dict[str, Any]], Awaitable[None]]):
        """Set callback for speech started events."""
        self.on_speech_started_callback = callback
    
    def set_speech_stopped_callback(self, callback: Callable[[Dict[str, Any]], Awaitable[None]]):
        """Set callback for speech stopped events."""
        self.on_speech_stopped_callback = callback
    
    async def connect(self):
        """Connect to the hearing event emitter via Unix Domain Socket."""
        max_retries = 10
        retry_delay = 2
        
        for attempt in range(max_retries):
            try:
                logger.info(f"Connecting to hearing service at {self.socket_path} (attempt {attempt + 1}/{max_retries})")
                
                # Check if socket file exists
                if not os.path.exists(self.socket_path):
                    logger.warning(f"Socket file does not exist: {self.socket_path}")
                else:
                    logger.info(f"Socket file exists: {self.socket_path}")
                    # Check file permissions
                    import stat
                    st = os.stat(self.socket_path)
                    logger.info(f"Socket permissions: {oct(st.st_mode)}")
                
                self.socket = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
                self.socket.connect(self.socket_path)
                self.socket.setblocking(False)
                
                logger.info("✓ Connected to hearing service")
                logger.info(f"   Socket FD: {self.socket.fileno()}")
                
                # Try to get peer name (Unix sockets don't really have this, but try anyway)
                try:
                    peer = self.socket.getpeername()
                    logger.info(f"   Peer: {peer}")
                except:
                    logger.info(f"   (Unix socket, no peer name)")
                
                return
                
            except (FileNotFoundError, ConnectionRefusedError) as e:
                logger.warning(f"Connection failed: {e}")
                if attempt < max_retries - 1:
                    logger.info(f"Retrying in {retry_delay} seconds...")
                    await asyncio.sleep(retry_delay)
                else:
                    raise RuntimeError(f"Failed to connect to hearing service after {max_retries} attempts")
            except Exception as e:
                logger.error(f"Unexpected error connecting to socket: {e}", exc_info=True)
                if attempt < max_retries - 1:
                    await asyncio.sleep(retry_delay)
                else:
                    raise
    
    async def listen(self):
        """Listen to events from the hearing service."""
        logger.info("Starting event listener...")
        logger.info(f"Socket file descriptor: {self.socket.fileno()}")
        logger.info(f"Socket is connected: {self.socket.getpeername() if hasattr(self.socket, 'getpeername') else 'unknown'}")
        
        event_count = 0
        last_data_time = asyncio.get_event_loop().time()
        
        while True:
            try:
                # Try to receive data (non-blocking)
                try:
                    data = await asyncio.to_thread(self.socket.recv, 4096)
                    
                    if not data:
                        logger.warning("Socket closed by server (received empty data)")
                        break
                    
                    current_time = asyncio.get_event_loop().time()
                    time_since_last = current_time - last_data_time
                    last_data_time = current_time
                    
                    logger.debug(f"Received {len(data)} bytes from socket (time since last: {time_since_last:.2f}s)")
                    
                    # Add to buffer
                    self.socket_buffer += data.decode('utf-8')
                    logger.debug(f"Buffer size: {len(self.socket_buffer)} chars")
                    
                    # Process complete lines (events)
                    lines_processed = 0
                    while '\n' in self.socket_buffer:
                        line, self.socket_buffer = self.socket_buffer.split('\n', 1)
                        if line.strip():
                            lines_processed += 1
                            event_count += 1
                            logger.info(f"Processing event #{event_count} from buffer")
                            await self._handle_event(line)
                    
                    if lines_processed > 0:
                        logger.debug(f"Processed {lines_processed} line(s), remaining buffer: {len(self.socket_buffer)} chars")
                            
                except BlockingIOError:
                    # No data available, sleep briefly
                    await asyncio.sleep(0.1)
                except Exception as recv_error:
                    logger.error(f"Error receiving data: {recv_error}", exc_info=True)
                    await asyncio.sleep(0.1)
                    
            except Exception as e:
                logger.error(f"Error in event listener main loop: {e}", exc_info=True)
                await asyncio.sleep(1)
        
        logger.warning(f"Event listener stopped after processing {event_count} events")
        await asyncio.sleep(0.1)
    
    async def _handle_event(self, event_line: str):
        """Handle a received event."""
        try:
            logger.debug(f"Parsing event line: {event_line[:100]}...")
            event = json.loads(event_line)
            event_type = event.get("type")
            event_data = event.get("data", {})
            
            logger.info(f"📡 Received event: {event_type}")
            logger.debug(f"   Full event: {event}")
            logger.debug(f"   Data: {event_data}")
            
            if event_type == "speech_started":
                await self._on_speech_started(event_data)
            elif event_type == "speech_stopped":
                await self._on_speech_stopped(event_data)
            else:
                logger.warning(f"Unknown event type: {event_type}")
                logger.debug(f"   Full unknown event: {event}")
                
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse event JSON: {e}")
            logger.error(f"   Raw data: {event_line}")
        except Exception as e:
            logger.error(f"Error handling event: {e}", exc_info=True)
            logger.error(f"   Event line was: {event_line}")
    
    async def _on_speech_started(self, data: Dict[str, Any]):
        """Handle speech started event."""
        print(data)
        event_number = data.get("event_number")
        timestamp = data.get("timestamp")
        
        logger.info(f"🎤 Speech started (Event #{event_number}) at {timestamp}")
        logger.debug(f"   Full data: {data}")
        
        # Store current speech event
        self.current_speech_event = {
            "event_number": event_number,
            "timestamp": timestamp,
            "start_time": timestamp
        }
        
        # User is speaking, Reachy should listen
        self.is_speaking = True
        logger.debug(f"   State updated: is_speaking={self.is_speaking}")
        
        # Call external callback if set
        if self.on_speech_started_callback:
            await self.on_speech_started_callback(data)
    
    async def _on_speech_stopped(self, data: Dict[str, Any]):
        """Handle speech stopped event."""
        print(data)
        event_number = data.get("event_number")
        duration = data.get("duration")
        timestamp = data.get("timestamp")
        
        logger.info(f"🔇 Speech stopped (Event #{event_number}) - Duration: {duration:.2f}s")
        logger.debug(f"   Full data: {data}")
        logger.debug(f"   Current state: is_speaking={self.is_speaking}, processing_speech={self.processing_speech}")
        
        # User finished speaking
        self.is_speaking = False
        
        # Prevent concurrent processing
        if self.processing_speech:
            logger.warning("Already processing speech, skipping this event")
            return
        
        # Process the speech event
        try:
            self.processing_speech = True
            logger.info(f"Starting speech processing for event #{event_number}")
            
            # Call external callback if set
            if self.on_speech_stopped_callback:
                await self.on_speech_stopped_callback(data)
            
            logger.info(f"Completed speech processing for event #{event_number}")
        except Exception as e:
            logger.error(f"Error processing speech event: {e}", exc_info=True)
        finally:
            self.processing_speech = False
            logger.debug(f"   State reset: processing_speech={self.processing_speech}")
    
    def close(self):
        """Close the socket connection."""
        if self.socket:
            try:
                self.socket.close()
                logger.info("Socket connection closed")
            except Exception as e:
                logger.warning(f"Error closing socket: {e}")
