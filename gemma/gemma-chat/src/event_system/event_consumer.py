"""Event consumer for receiving events from the event manager"""

import asyncio
import socket
import logging
from typing import Optional, Callable, Dict, List
from asyncio import Queue

from .event_types import GemmaEvent, EventType
from ..config import Config

class EventConsumer:
    """Consumes events from the event manager"""
    
    def __init__(self, config: Config, consumer_name: str = "unknown"):
        self.config = config
        self.consumer_name = consumer_name
        self.logger = logging.getLogger(f"{__name__}.{consumer_name}")
        self.socket_path = config.EVENT_SOCKET_PATH
        self.client_socket: Optional[socket.socket] = None
        self.connected = False
        self.running = False
        
        # Event handling
        self.handlers: Dict[EventType, List[Callable]] = {}
        self.event_queue: Queue = Queue()
    
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
        self.running = False
        if self.client_socket:
            try:
                self.client_socket.close()
            except:
                pass
            self.client_socket = None
            self.connected = False
            self.logger.info("Disconnected from event manager")
    
    async def start_consuming(self):
        """Start consuming events from the event manager"""
        if not self.connected:
            if not await self.connect():
                return
        
        self.running = True
        
        # Start receiving events
        asyncio.create_task(self._receive_events())
        
        # Start processing events
        asyncio.create_task(self._process_events())
        
        self.logger.info("Started consuming events")
    
    async def stop_consuming(self):
        """Stop consuming events"""
        self.running = False
        await self.disconnect()
        self.logger.info("Stopped consuming events")
    
    async def _receive_events(self):
        """Receive events from the event manager"""
        while self.running and self.connected:
            try:
                data = await asyncio.get_event_loop().sock_recv(
                    self.client_socket, self.config.EVENT_BUFFER_SIZE
                )
                if not data:
                    break
                
                try:
                    event_json = data.decode('utf-8')
                    event = GemmaEvent.from_json(event_json)
                    await self.event_queue.put(event)
                except Exception as e:
                    self.logger.error(f"Error parsing event: {e}")
                    
            except Exception as e:
                if self.running:
                    self.logger.error(f"Error receiving events: {e}")
                    self.connected = False
                break
    
    async def _process_events(self):
        """Process events from the queue"""
        while self.running:
            try:
                event = await asyncio.wait_for(self.event_queue.get(), timeout=1.0)
                await self._handle_event(event)
            except asyncio.TimeoutError:
                continue
            except Exception as e:
                self.logger.error(f"Error processing event: {e}")
    
    async def _handle_event(self, event: GemmaEvent):
        """Handle a specific event by calling registered handlers"""
        if event.event_type in self.handlers:
            for handler in self.handlers[event.event_type]:
                try:
                    if asyncio.iscoroutinefunction(handler):
                        await handler(event)
                    else:
                        handler(event)
                except Exception as e:
                    self.logger.error(f"Error in event handler: {e}")
    
    def register_handler(self, event_type: EventType, handler: Callable):
        """Register an event handler"""
        if event_type not in self.handlers:
            self.handlers[event_type] = []
        self.handlers[event_type].append(handler)
        self.logger.debug(f"Registered handler for {event_type}")
    
    def unregister_handler(self, event_type: EventType, handler: Callable):
        """Unregister an event handler"""
        if event_type in self.handlers:
            try:
                self.handlers[event_type].remove(handler)
                if not self.handlers[event_type]:
                    del self.handlers[event_type]
                self.logger.debug(f"Unregistered handler for {event_type}")
            except ValueError:
                self.logger.warning(f"Handler not found for {event_type}")
    
    async def get_next_event(self, timeout: float = 1.0) -> Optional[GemmaEvent]:
        """Get the next event from the queue"""
        try:
            return await asyncio.wait_for(self.event_queue.get(), timeout=timeout)
        except asyncio.TimeoutError:
            return None