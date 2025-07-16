"""Event manager for handling Unix domain socket communication"""

import asyncio
import socket
import os
import logging
from typing import Dict, List, Callable, Optional, Any
from asyncio import Queue
import json
import time
from dataclasses import asdict

from .event_types import GemmaEvent, EventType
from ..config import Config

class EventManager:
    """Manages event distribution using Unix domain sockets"""
    
    def __init__(self, config: Config):
        self.config = config
        self.logger = logging.getLogger(__name__)
        self.socket_path = config.EVENT_SOCKET_PATH
        self.server_socket: Optional[socket.socket] = None
        self.clients: Dict[str, socket.socket] = {}
        self.event_queue: Queue = Queue()
        self.handlers: Dict[EventType, List[Callable]] = {}
        self.running = False
        
        # Priority queue for events (higher priority processed first)
        self.priority_queue: List[GemmaEvent] = []
        
    async def start(self):
        """Start the event manager server"""
        self.logger.info(f"Starting event manager on {self.socket_path}")
        
        # Remove existing socket file if it exists
        if os.path.exists(self.socket_path):
            os.unlink(self.socket_path)
        
        # Create Unix domain socket
        self.server_socket = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self.server_socket.bind(self.socket_path)
        self.server_socket.listen(5)
        self.server_socket.setblocking(False)
        
        self.running = True
        
        # Start event processing loop
        asyncio.create_task(self._process_events())
        
        # Start accepting connections
        asyncio.create_task(self._accept_connections())
        
        self.logger.info("Event manager started successfully")
    
    async def stop(self):
        """Stop the event manager"""
        self.logger.info("Stopping event manager")
        self.running = False
        
        # Close all client connections
        for client_id, client_socket in self.clients.items():
            try:
                client_socket.close()
            except Exception as e:
                self.logger.warning(f"Error closing client {client_id}: {e}")
        
        # Close server socket
        if self.server_socket:
            self.server_socket.close()
            
        # Remove socket file
        if os.path.exists(self.socket_path):
            os.unlink(self.socket_path)
        
        self.logger.info("Event manager stopped")
    
    async def _accept_connections(self):
        """Accept new client connections"""
        while self.running:
            try:
                client_socket, _ = await asyncio.get_event_loop().sock_accept(self.server_socket)
                client_id = f"client_{len(self.clients)}"
                self.clients[client_id] = client_socket
                
                self.logger.debug(f"New client connected: {client_id}")
                
                # Start handling client messages
                asyncio.create_task(self._handle_client(client_id, client_socket))
                
            except Exception as e:
                if self.running:
                    self.logger.error(f"Error accepting connection: {e}")
                await asyncio.sleep(0.1)
    
    async def _handle_client(self, client_id: str, client_socket: socket.socket):
        """Handle messages from a specific client"""
        try:
            while self.running:
                data = await asyncio.get_event_loop().sock_recv(client_socket, self.config.EVENT_BUFFER_SIZE)
                if not data:
                    break
                
                try:
                    event_json = data.decode('utf-8')
                    event = GemmaEvent.from_json(event_json)
                    await self._add_event(event)
                except Exception as e:
                    self.logger.error(f"Error processing event from {client_id}: {e}")
                    
        except Exception as e:
            self.logger.error(f"Error handling client {client_id}: {e}")
        finally:
            # Clean up client connection
            if client_id in self.clients:
                del self.clients[client_id]
            try:
                client_socket.close()
            except:
                pass
            self.logger.debug(f"Client {client_id} disconnected")
    
    async def _add_event(self, event: GemmaEvent):
        """Add event to priority queue"""
        # Insert event based on priority (higher priority first)
        inserted = False
        for i, existing_event in enumerate(self.priority_queue):
            if event.priority > existing_event.priority:
                self.priority_queue.insert(i, event)
                inserted = True
                break
        
        if not inserted:
            self.priority_queue.append(event)
        
        # Also add to regular queue for backwards compatibility
        await self.event_queue.put(event)
    
    async def _process_events(self):
        """Process events from the queue"""
        while self.running:
            try:
                # Process priority queue first
                if self.priority_queue:
                    event = self.priority_queue.pop(0)
                    await self._handle_event(event)
                else:
                    # Wait for new events
                    await asyncio.sleep(0.01)
                    
            except Exception as e:
                self.logger.error(f"Error processing events: {e}")
                await asyncio.sleep(0.1)
    
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
        
        # Broadcast event to all connected clients
        await self._broadcast_event(event)
    
    async def _broadcast_event(self, event: GemmaEvent):
        """Broadcast event to all connected clients"""
        if not self.clients:
            return
        
        event_json = event.to_json().encode('utf-8')
        
        # Send to all clients
        disconnected_clients = []
        for client_id, client_socket in self.clients.items():
            try:
                await asyncio.get_event_loop().sock_sendall(client_socket, event_json)
            except Exception as e:
                self.logger.warning(f"Error sending to client {client_id}: {e}")
                disconnected_clients.append(client_id)
        
        # Remove disconnected clients
        for client_id in disconnected_clients:
            del self.clients[client_id]
    
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
    
    async def publish_event(self, event: GemmaEvent):
        """Publish an event to the system"""
        await self._add_event(event)
        self.logger.debug(f"Published event: {event.event_type}")
    
    async def get_next_event(self) -> Optional[GemmaEvent]:
        """Get the next event from the queue"""
        try:
            return await asyncio.wait_for(self.event_queue.get(), timeout=1.0)
        except asyncio.TimeoutError:
            return None