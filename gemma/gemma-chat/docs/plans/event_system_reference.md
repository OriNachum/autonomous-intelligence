# Event System Reference - From TauLegacy

This document contains the key event system implementation patterns from TauLegacy that should be used as reference for the Gemma project.

## Core Event Handler Pattern

### Basic Event Handler (event_handler.py)
```python
import socket
import selectors
import os
import sys
import logging

class EventHandler:
    def __init__(self, socket_path="./sockets/tau_hearing_socket"):
        self.socket_path = socket_path
        self.selector = selectors.DefaultSelector()
        self.setup_socket()
        
    def setup_socket(self):
        # Remove existing socket file
        if os.path.exists(self.socket_path):
            os.unlink(self.socket_path)
            
        # Create socket directory if it doesn't exist
        os.makedirs(os.path.dirname(self.socket_path), exist_ok=True)
        
        # Create and bind socket
        self.sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self.sock.bind(self.socket_path)
        self.sock.listen(1)
        self.sock.setblocking(False)
        
        # Register with selector
        self.selector.register(self.sock, selectors.EVENT_READ, data=None)
        
    def accept_wrapper(self, sock):
        """Accept new connections"""
        conn, addr = sock.accept()
        conn.setblocking(False)
        data = types.SimpleNamespace(addr=addr, inb=b'', outb=b'')
        events = selectors.EVENT_READ | selectors.EVENT_WRITE
        self.selector.register(conn, events, data=data)
        
    def service_connection(self, key, mask):
        """Handle existing connections"""
        sock = key.fileobj
        data = key.data
        
        if mask & selectors.EVENT_READ:
            recv_data = sock.recv(1024)
            if recv_data:
                data.inb += recv_data
                # Process the received data
                message = data.inb.decode('utf-8')
                self.process_event(message)
                data.inb = b''  # Clear buffer
            else:
                # Connection closed
                self.selector.unregister(sock)
                sock.close()
                
    def process_event(self, message):
        """Process incoming event messages"""
        if "Speech started" in message:
            print(f"Event: {message}")
        elif "Speech stopped" in message:
            print(f"Event: {message}")
            
    def run(self):
        """Main event loop"""
        try:
            while True:
                events = self.selector.select(timeout=1)
                for key, mask in events:
                    if key.data is None:
                        self.accept_wrapper(key.fileobj)
                    else:
                        self.service_connection(key, mask)
        except KeyboardInterrupt:
            print("Shutting down...")
        finally:
            self.selector.close()
            self.sock.close()
            if os.path.exists(self.socket_path):
                os.unlink(self.socket_path)
```

## Event Listener Client Pattern

### Event Listener Service (services/event_listener.py)
```python
import socket
import selectors
import threading
import time
import logging

class EventListener:
    def __init__(self, socket_path, selector, callback):
        self.socket_path = socket_path
        self.selector = selector
        self.callback = callback
        self.last_event = None
        self.running = False
        self.thread = None
        self.sock = None
        
    def start(self):
        """Start the event listener in a separate thread"""
        self.running = True
        self.thread = threading.Thread(target=self._run, daemon=True)
        self.thread.start()
        
    def stop(self):
        """Stop the event listener"""
        self.running = False
        if self.thread:
            self.thread.join()
            
    def _run(self):
        """Main event listening loop"""
        while self.running:
            try:
                self._connect()
                self._listen()
            except Exception as e:
                logging.error(f"Event listener error: {e}")
                time.sleep(1)  # Wait before reconnecting
                
    def _connect(self):
        """Connect to the event socket"""
        if self.sock:
            self.sock.close()
            
        self.sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self.sock.connect(self.socket_path)
        self.sock.setblocking(False)
        
        # Register with selector
        self.selector.register(self.sock, selectors.EVENT_READ, data=self)
        
    def _listen(self):
        """Listen for events"""
        while self.running:
            events = self.selector.select(timeout=1)
            for key, mask in events:
                if key.data == self and mask & selectors.EVENT_READ:
                    self._handle_event(key.fileobj)
                    
    def _handle_event(self, sock):
        """Handle incoming events"""
        try:
            data = sock.recv(1024)
            if data:
                message = data.decode('utf-8')
                self.last_event = message
                self.callback(message)
            else:
                # Connection closed, need to reconnect
                self.selector.unregister(sock)
                sock.close()
                self.sock = None
                raise ConnectionError("Connection closed")
        except Exception as e:
            logging.error(f"Error handling event: {e}")
            raise
```

## Speech Detection Event Producer

### Microphone Listener (services/microphone-listener.py)
```python
import asyncio
import socket
import webrtcvad
import wave
import time
import logging
from collections import deque

class SpeechDetector:
    def __init__(self, socket_path="./sockets/tau_hearing_socket"):
        self.socket_path = socket_path
        self.vad = webrtcvad.Vad(2)  # Aggressiveness level
        self.speech_events = 0
        self.is_speaking = False
        self.speech_buffer = deque(maxlen=100)  # Circular buffer
        self.sock = None
        self.setup_socket()
        
    def setup_socket(self):
        """Setup client socket for sending events"""
        try:
            self.sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            self.sock.connect(self.socket_path)
            logging.info(f"Connected to event socket: {self.socket_path}")
        except Exception as e:
            logging.error(f"Failed to connect to event socket: {e}")
            
    def send_event(self, event_message):
        """Send event to the event system"""
        if self.sock:
            try:
                self.sock.sendall(event_message.encode('utf-8'))
                logging.info(f"Sent event: {event_message}")
            except Exception as e:
                logging.error(f"Failed to send event: {e}")
                
    def log_speech_event(self, event_type, transcript=None):
        """Log speech events with timestamps"""
        current_time = time.strftime("%Y-%m-%d %H:%M:%S")
        
        if event_type == "start":
            self.speech_events += 1
            message = f"[{current_time}] Speech started (Event #{self.speech_events})"
            self.send_event(message)
            
        elif event_type == "stop":
            if transcript:
                message = f"[{current_time}] Speech stopped - Transcript: {transcript}"
            else:
                message = f"[{current_time}] Speech stopped (Event #{self.speech_events})"
            self.send_event(message)
            
    async def process_audio_stream(self, audio_stream):
        """Process audio stream for speech detection"""
        frame_duration = 30  # ms
        frame_size = int(16000 * frame_duration / 1000)  # 16kHz sample rate
        
        async for audio_chunk in audio_stream:
            # Convert to appropriate format for VAD
            audio_data = self._convert_audio_format(audio_chunk)
            
            # Detect speech
            is_speech = self.vad.is_speech(audio_data, 16000)
            
            if is_speech and not self.is_speaking:
                # Speech started
                self.is_speaking = True
                self.speech_buffer.clear()
                self.log_speech_event("start")
                
            elif not is_speech and self.is_speaking:
                # Speech stopped
                self.is_speaking = False
                transcript = await self._transcribe_buffer()
                self.log_speech_event("stop", transcript)
                
            # Add to buffer if speaking
            if self.is_speaking:
                self.speech_buffer.append(audio_data)
                
    def _convert_audio_format(self, audio_chunk):
        """Convert audio chunk to format suitable for VAD"""
        # Implementation depends on input format
        # This is a placeholder
        return audio_chunk
        
    async def _transcribe_buffer(self):
        """Transcribe accumulated speech buffer"""
        if not self.speech_buffer:
            return None
            
        # Combine buffer into single audio file
        audio_data = b''.join(self.speech_buffer)
        
        # Use OpenAI Whisper or similar for transcription
        # This is a placeholder
        return "Transcribed text here"
```

## Event Message Formats

### Standard Event Messages
```python
# Speech Events
SPEECH_START = "[{timestamp}] Speech started (Event #{event_number})"
SPEECH_STOP = "[{timestamp}] Speech stopped - Transcript: {transcript}"

# Vision Events (JSON format)
VISION_EVENT = {
    "event_type": "object_detected",
    "timestamp": 1704110400.0,
    "data": {
        "objects": ["person", "car"],
        "confidence": 0.95,
        "bounding_boxes": [...]
    }
}

# Action Events
ACTION_EVENT = {
    "event_type": "action_required",
    "timestamp": 1704110400.0,
    "data": {
        "action": "speak",
        "content": "Hello, how can I help you?",
        "priority": "high"
    }
}
```

## Integration Patterns

### Main Event Loop Integration (tau.py)
```python
import asyncio
import selectors
from event_handler import EventHandler
from event_listener import EventListener

class TauEventSystem:
    def __init__(self):
        self.selector = selectors.DefaultSelector()
        self.event_handler = EventHandler()
        self.event_listeners = []
        self.running = False
        
    def add_event_listener(self, socket_path, callback):
        """Add event listener for specific socket"""
        listener = EventListener(socket_path, self.selector, callback)
        self.event_listeners.append(listener)
        return listener
        
    def external_event_callback(self, event_data):
        """Handle external events from vision, audio, etc."""
        logging.info(f"External event received: {event_data}")
        # Process and route event to appropriate handler
        
    async def main_loop(self):
        """Main event processing loop"""
        # Start event handler
        event_handler_task = asyncio.create_task(self.event_handler.run())
        
        # Start event listeners
        for listener in self.event_listeners:
            listener.start()
            
        # Setup vision event listener
        vision_listener = self.add_event_listener(
            "./sockets/vision_socket", 
            self.external_event_callback
        )
        
        # Main processing loop
        self.running = True
        while self.running:
            try:
                # Process events and handle AI responses
                await self.process_events()
                await asyncio.sleep(0.1)  # Small delay to prevent busy waiting
                
            except KeyboardInterrupt:
                logging.info("Shutting down...")
                self.running = False
                
        # Cleanup
        for listener in self.event_listeners:
            listener.stop()
            
    async def process_events(self):
        """Process collected events and generate AI responses"""
        # This is where the main AI processing would happen
        # Get events, process with model, generate responses
        pass
```

## Socket Paths and Configuration

### Standard Socket Paths
```python
# Event System Socket Paths
SOCKETS = {
    "main_event": "./sockets/tau_hearing_socket",
    "vision": "./sockets/vision_socket", 
    "face_expression": "./uds_socket",
    "gstreamer": "/tmp/gst_detection.sock",
    "text_input": "./sockets/text_input_socket",
    "action_output": "./sockets/action_output_socket"
}

# Create socket directory
import os
for socket_path in SOCKETS.values():
    os.makedirs(os.path.dirname(socket_path), exist_ok=True)
```

## Key Implementation Notes

1. **Non-blocking I/O**: All socket operations use non-blocking mode with selectors
2. **Error Handling**: Comprehensive error handling with automatic reconnection
3. **Threading**: Event listeners run in separate daemon threads
4. **Event Buffering**: Circular buffers for audio data and event queuing
5. **Clean Shutdown**: Proper cleanup of sockets and threads
6. **Message Formats**: Consistent timestamp and event numbering
7. **Socket Management**: Automatic socket file cleanup and directory creation

This reference implementation provides a solid foundation for implementing the event system in the Gemma project.