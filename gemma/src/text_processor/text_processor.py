"""Text input processing loop"""

import asyncio
import logging
import sys
from typing import Optional, Dict, Any, List
import threading
import time
from queue import Queue as ThreadQueue

from ..event_system import EventProducer, EventType, TextEvent
from ..config import Config

class TextProcessor:
    """Text input processing from terminal"""
    
    def __init__(self, config: Config):
        self.config = config
        self.logger = logging.getLogger(__name__)
        
        # Event system
        self.event_producer = EventProducer(config, "text_processor")
        
        # Processing state
        self.running = False
        self.processing_active = False
        
        # Input handling
        self.input_queue = ThreadQueue()
        self.input_thread: Optional[threading.Thread] = None
        
        # Text processing
        self.text_history: List[str] = []
        self.max_history = 100
        
        # Statistics
        self.processed_inputs = 0
        self.last_input_time = 0
        self.input_lengths = []
        
        # Special commands
        self.special_commands = {
            '/quit': self._handle_quit,
            '/exit': self._handle_quit,
            '/help': self._handle_help,
            '/status': self._handle_status,
            '/clear': self._handle_clear,
            '/history': self._handle_history,
            '/reset': self._handle_reset
        }
    
    async def start(self):
        """Start text processing"""
        self.logger.info("Starting text processor")
        
        # Connect to event system
        await self.event_producer.connect()
        
        self.running = True
        self.processing_active = True
        
        # Start input thread
        self.input_thread = threading.Thread(target=self._input_loop, daemon=True)
        self.input_thread.start()
        
        # Start processing loop
        asyncio.create_task(self._processing_loop())
        
        self.logger.info("Text processor started")
        self._show_welcome()
        return True
    
    async def stop(self):
        """Stop text processing"""
        self.logger.info("Stopping text processor")
        
        self.running = False
        self.processing_active = False
        
        # Wait for input thread
        if self.input_thread and self.input_thread.is_alive():
            self.input_thread.join(timeout=1.0)
        
        # Disconnect from event system
        await self.event_producer.disconnect()
        
        self.logger.info("Text processor stopped")
    
    def _show_welcome(self):
        """Show welcome message"""
        print("\n" + "="*50)
        print("         GEMMA TEXT INPUT")
        print("="*50)
        print("Type your messages and press Enter to send.")
        print("Special commands:")
        print("  /help    - Show this help")
        print("  /status  - Show system status")
        print("  /clear   - Clear screen")
        print("  /history - Show input history")
        print("  /reset   - Reset conversation")
        print("  /quit    - Exit application")
        print("="*50)
        print()
    
    def _input_loop(self):
        """Input loop running in separate thread"""
        while self.running:
            try:
                # Display prompt
                print("Gemma> ", end="", flush=True)
                
                # Read input
                user_input = input().strip()
                
                if user_input:
                    self.input_queue.put(user_input)
                    self.last_input_time = time.time()
                
            except EOFError:
                # Handle Ctrl+D
                self.input_queue.put('/quit')
                break
            except KeyboardInterrupt:
                # Handle Ctrl+C
                self.input_queue.put('/quit')
                break
            except Exception as e:
                self.logger.error(f"Error in input loop: {e}")
                time.sleep(0.1)
    
    async def _processing_loop(self):
        """Main text processing loop"""
        while self.processing_active:
            try:
                # Get input
                text_input = await self._get_text_input()
                if text_input is None:
                    await asyncio.sleep(0.1)
                    continue
                
                # Process input
                await self._process_text_input(text_input)
                
            except Exception as e:
                self.logger.error(f"Error in processing loop: {e}")
                await asyncio.sleep(0.1)
    
    async def _get_text_input(self) -> Optional[str]:
        """Get text input from queue"""
        try:
            if not self.input_queue.empty():
                return self.input_queue.get_nowait()
        except:
            pass
        return None
    
    async def _process_text_input(self, text_input: str):
        """Process a single text input"""
        try:
            # Add to history
            self.text_history.append(text_input)
            if len(self.text_history) > self.max_history:
                self.text_history.pop(0)
            
            # Update statistics
            self.processed_inputs += 1
            self.input_lengths.append(len(text_input))
            if len(self.input_lengths) > 100:
                self.input_lengths.pop(0)
            
            # Check for special commands
            if text_input.startswith('/'):
                await self._handle_special_command(text_input)
                return
            
            # Send text event
            await self._send_text_event(text_input)
            
            self.logger.debug(f"Processed text input: {text_input}")
            
        except Exception as e:
            self.logger.error(f"Error processing text input: {e}")
    
    async def _send_text_event(self, text: str):
        """Send text input event"""
        try:
            text_event = TextEvent(
                event_type=EventType.TEXT_INPUT,
                text=text
            )
            await self.event_producer.send_event(text_event)
            self.logger.debug(f"Sent text event: {text}")
            
        except Exception as e:
            self.logger.error(f"Error sending text event: {e}")
    
    async def _handle_special_command(self, command: str):
        """Handle special commands"""
        cmd_parts = command.split()
        cmd = cmd_parts[0].lower()
        
        if cmd in self.special_commands:
            await self.special_commands[cmd](cmd_parts)
        else:
            print(f"Unknown command: {cmd}")
            print("Type /help for available commands")
    
    async def _handle_quit(self, cmd_parts: List[str]):
        """Handle quit command"""
        print("Goodbye!")
        self.running = False
        self.processing_active = False
        # Send system shutdown event
        try:
            from ..event_system.event_types import GemmaEvent
            shutdown_event = GemmaEvent(
                event_type=EventType.SYSTEM_SHUTDOWN,
                timestamp=time.time(),
                data={'reason': 'user_quit'}
            )
            await self.event_producer.send_event(shutdown_event)
        except:
            pass
    
    async def _handle_help(self, cmd_parts: List[str]):
        """Handle help command"""
        print("\nGemma Text Input Help")
        print("=" * 30)
        print("Available commands:")
        print("  /help    - Show this help message")
        print("  /status  - Show system status")
        print("  /clear   - Clear the screen")
        print("  /history - Show recent input history")
        print("  /reset   - Reset the conversation")
        print("  /quit    - Exit the application")
        print("\nJust type your message and press Enter to chat with Gemma!")
        print()
    
    async def _handle_status(self, cmd_parts: List[str]):
        """Handle status command"""
        status = self.get_status()
        print("\nText Processor Status")
        print("=" * 25)
        print(f"Running: {status['running']}")
        print(f"Processed inputs: {status['processed_inputs']}")
        print(f"History size: {len(status['text_history'])}")
        print(f"Last input: {status['last_input_time']}")
        if status['input_lengths']:
            avg_length = sum(status['input_lengths']) / len(status['input_lengths'])
            print(f"Average input length: {avg_length:.1f} characters")
        print()
    
    async def _handle_clear(self, cmd_parts: List[str]):
        """Handle clear command"""
        # Clear screen
        print("\033[2J\033[H", end="")
        self._show_welcome()
    
    async def _handle_history(self, cmd_parts: List[str]):
        """Handle history command"""
        if not self.text_history:
            print("No input history available")
            return
        
        print("\nRecent Input History")
        print("=" * 25)
        # Show last 10 inputs
        recent_history = self.text_history[-10:]
        for i, text in enumerate(recent_history, 1):
            print(f"{i:2d}. {text}")
        print()
    
    async def _handle_reset(self, cmd_parts: List[str]):
        """Handle reset command"""
        print("Resetting conversation...")
        
        # Clear local history
        self.text_history = []
        
        # Send reset event
        try:
            from ..event_system.event_types import GemmaEvent
            reset_event = GemmaEvent(
                event_type=EventType.RESET_QUEUE,  # Reuse this event type
                timestamp=time.time(),
                data={'type': 'conversation_reset'}
            )
            await self.event_producer.send_event(reset_event)
        except Exception as e:
            self.logger.error(f"Error sending reset event: {e}")
        
        print("Conversation reset complete")
    
    def get_status(self) -> Dict[str, Any]:
        """Get text processor status"""
        return {
            'running': self.running,
            'processed_inputs': self.processed_inputs,
            'last_input_time': self.last_input_time,
            'text_history': self.text_history.copy(),
            'input_lengths': self.input_lengths.copy(),
            'history_size': len(self.text_history),
            'queue_size': self.input_queue.qsize()
        }
    
    def get_recent_history(self, count: int = 10) -> List[str]:
        """Get recent input history"""
        return self.text_history[-count:] if self.text_history else []
    
    def clear_history(self):
        """Clear input history"""
        self.text_history = []
        self.logger.info("Text input history cleared")
    
    def add_special_command(self, command: str, handler):
        """Add a custom special command"""
        self.special_commands[command] = handler
        self.logger.info(f"Added special command: {command}")
    
    def remove_special_command(self, command: str):
        """Remove a special command"""
        if command in self.special_commands:
            del self.special_commands[command]
            self.logger.info(f"Removed special command: {command}")
    
    def send_message(self, message: str):
        """Programmatically send a message"""
        if self.running:
            self.input_queue.put(message)
            self.logger.debug(f"Programmatically sent message: {message}")