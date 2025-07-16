"""Event producer for sending events to the event manager"""

import asyncio
import socket
import logging
from typing import Optional

from .event_types import GemmaEvent
from ..config import Config

class EventProducer:
    """Produces events and sends them to the event manager"""
    
    def __init__(self, config: Config, producer_name: str = "unknown"):
        self.config = config
        self.producer_name = producer_name
        self.logger = logging.getLogger(f"{__name__}.{producer_name}")
        self.socket_path = config.EVENT_SOCKET_PATH
        self.client_socket: Optional[socket.socket] = None
        self.connected = False
    
    async def connect(self) -> bool:
        """Connect to the event manager"""
        try:
            self.client_socket = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            self.client_socket.setblocking(False)
            await asyncio.get_event_loop().sock_connect(self.client_socket, self.socket_path)
            self.connected = True
            self.logger.info(f"Connected to event manager")
            return True
        except Exception as e:
            self.logger.error(f"Failed to connect to event manager: {e}")
            self.connected = False
            return False
    
    async def disconnect(self):
        """Disconnect from the event manager"""
        if self.client_socket:
            try:
                self.client_socket.close()
            except:
                pass
            self.client_socket = None
            self.connected = False
            self.logger.info("Disconnected from event manager")
    
    async def send_event(self, event: GemmaEvent) -> bool:
        """Send an event to the event manager"""
        if not self.connected:
            await self.connect()
        
        if not self.connected:
            self.logger.warning("Cannot send event - not connected to event manager")
            return False
        
        try:
            # Set event source
            event.source = self.producer_name
            
            # Send event
            event_json = event.to_json().encode('utf-8')
            await asyncio.get_event_loop().sock_sendall(self.client_socket, event_json)
            
            self.logger.debug(f"Sent event: {event.event_type}")
            return True
            
        except Exception as e:
            self.logger.error(f"Failed to send event: {e}")
            self.connected = False
            return False
    
    async def ensure_connected(self) -> bool:
        """Ensure connection to event manager"""
        if not self.connected:
            return await self.connect()
        return True