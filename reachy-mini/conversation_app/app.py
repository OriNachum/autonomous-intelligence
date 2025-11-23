#!/usr/bin/env python3
"""
Conversation Application with Speech Event Integration

This application listens to speech events from the hearing_event_emitter service
and processes them through the vLLM streaming chat system.

Instead of accepting text input from the user, this app responds to speech
detection events emitted via Unix Domain Socket.

Key features:
1. Listens to speech_started/speech_stopped events
2. Processes speech events through vLLM streaming chat completion
3. Parses responses for quotes "..." (speech) and **...** (actions)
4. Queues speech and actions for separate processing
5. Automatic conversation flow based on speech detection

Output format:
- Text in quotes "..." -> Speech queue (for TTS)
- Text in **...** -> Action queue (for movement)

Usage:
    python -m conversation_app.app
    # or from root
    python conversation_app.py
    
Requirements:
    - Hearing event emitter running (hearing_event_emitter.py)
    - vLLM server running on http://localhost:8100 with streaming support
"""

import asyncio
import json
import httpx
import traceback
import os
import sys
from pathlib import Path
from typing import List, Dict, Any
import logging
from reachy_mini.utils.interpolation import InterpolationTechnique

# Ensure gateway_app is importable
sys.path.insert(0, '/app')

from .conversation_parser import ConversationParser
from .speech_handler import SpeechHandler
from .action_handler import ActionHandler
from .gateway import ReachyGateway


# Set up logging
logging.basicConfig(
    level=logging.ERROR,  # Changed to DEBUG for detailed logging
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Configuration
CHAT_COMPLETIONS_URL = os.environ.get("VLLM_FRONT_URL", "http://localhost:8100/v1/chat/completions")
MODEL_NAME = os.environ.get("MODEL_ID", "RedHatAI/Llama-3.2-3B-Instruct-FP8")
AGENT_TEMPERATURE = 0.3

class ConversationApp:
    """Conversation application with speech event integration."""
    
    def __init__(self):
        """
        Initialize the conversation application.
        """
        self.messages = []
        
        # Load the system prompt
        self.system_prompt = Path("/app/conversation_app/agents/reachy/reachy.system.md").read_text()
        
        # Initialize components
        self.gateway = None  # Will be initialized in initialize()
        self.parser = ConversationParser()
        self.speech_handler = None  # Will be initialized in initialize()
        self.action_handler = None  # Will be initialized in initialize()

    async def initialize(self):
        """Initialize the application."""
        logger.info("=" * 70)
        logger.info("Initializing Conversation App")
        logger.info("=" * 70)
        
        # Initialize conversation with system prompt
        self.messages = [
            {"role": "system", "content": self.system_prompt}
        ]
        
        # Initialize ReachyGateway with callback
        try:
            device_name = os.getenv('AUDIO_DEVICE_NAME', 'Reachy')
            language = os.getenv('LANGUAGE', 'en')
            
            self.gateway = ReachyGateway(
                device_name=device_name,
                language=language,
                event_callback=self.on_gateway_event,
                enable_socket_server=False  # Use callback mode only
            )
            logger.info("✓ Reachy Gateway initialized")
            #self.gateway.move_cyclically(duration=10.0, repetitions=3, roll=0.0, pitch=10.0, yaw=10.0, antennas=[25.0, 25.0], body_yaw=0.0)
            #self.gateway.move_smoothly_to(duration=2.0, roll=-0.3, pitch=-0.2, yaw=0.2, antennas=[1.0, 1.0], body_yaw=30.0)
        except Exception as e:
            logger.error(f"❌ Failed to initialize gateway: {e}")
            raise
        
        # Initialize speech handler
        try:
            self.speech_handler = SpeechHandler()
            logger.info("✓ Speech handler initialized")
        except Exception as e:
            logger.error(f"❌ Failed to initialize speech handler: {e}")
            logger.warning("   Continuing without TTS...")
            self.speech_handler = None
        
        # Initialize action handler
        try:
            self.action_handler = ActionHandler(gateway=self.gateway)
            # Warm up action handler in background
            #asyncio.create_task(self.action_handler.execute("nod head"))

            logger.info("✓ Action handler initialized")
        except Exception as e:
            logger.error(f"❌ Failed to initialize action handler: {e}")
            logger.warning("   Continuing without action execution...")
            self.action_handler = None
        
        logger.info("✓ App initialized")
        logger.info("=" * 70)
    
    def _trim_conversation_history(self):
        """
        Trim conversation history to keep system message + last 9 messages.
        This maintains context while preventing unbounded growth.
        Format: [system, user, assistant, user, assistant, ..., user, assistant, user]
        Total: 10 messages (1 system + 9 conversation messages = ~4.5 pairs)
        """
        if len(self.messages) <= 10:
            return
        
        # Keep system message (index 0) and last 9 messages
        system_message = self.messages[0]
        recent_messages = self.messages[-9:]
        
        self.messages = [system_message] + recent_messages
        logger.debug(f"Trimmed conversation history to {len(self.messages)} messages")
    
    async def on_gateway_event(self, event_type: str, data: Dict[str, Any]):
        """
        Route gateway events to appropriate handlers.
        
        Args:
            event_type: Type of event (speech_started, speech_stopped, etc.)
            data: Event data
        """
        if event_type == "speech_started":
            await self.on_speech_started(data)
        elif event_type == "speech_stopped":
            await self.on_speech_stopped(data)
        elif event_type == "speech_ongoing":
            # Optional: handle ongoing events
            pass
        elif event_type == "speech_partial":
            # Optional: handle partial transcriptions
            pass
        else:
            logger.debug(f"Unhandled event type: {event_type}")
    
    async def _warm_up_for_caching(self, last_assistant_response: str) -> str:
        """
        Send a dummy request to warm up the model for caching next token prediction.
        
        Args:
            last_assistan_response: The full assistant response text
        """

                # send dummy request for next token caching with assistant response + "." as user message
        async with httpx.AsyncClient(timeout=60.0) as client:
            # message minus first two message plus system as first message
            # Include the assistant's response and append "." as a dummy user message for caching
            cache_messages = self.messages
            
            cache_messages += [
                {"role": "assistant", "content": last_assistant_response},
                {"role": "user", "content": "."}
            ]

            if len(cache_messages) > 10:
                system_message = self.messages[0]
                recent_messages = self.messages[-9:]
        
                cache_messages = [system_message] + recent_messages
            
            payload = {
                "model": MODEL_NAME,
                "messages": cache_messages,
                "max_tokens": 1,
                "temperature": AGENT_TEMPERATURE,
                "stream": False
            }
            try:
                response = await client.post(CHAT_COMPLETIONS_URL, json=payload)
                response.raise_for_status()
            except Exception as e:
                logger.error(f"Error during dummy request for caching: {e}")
                raise


    async def on_speech_started(self, data: Dict[str, Any]):
        """
        Callback for speech started events.
        
        Args:
            data: Event data containing event_number, timestamp, etc.
        """
        # Clear TTS queue when user starts speaking to avoid talking over them
        if self.speech_handler:
            logger.info("🔇 User started speaking - clearing TTS queue")
            await self.speech_handler.clear()
        
        # Clear action queue when user starts speaking to stop current actions
        if self.action_handler:
            logger.info("🚫 User started speaking - clearing action queue")
            await self.action_handler.clear()
    
    async def on_speech_stopped(self, data: Dict[str, Any]):
        """
        Callback for speech stopped events - trigger conversation processing.
        
        Args:
            data: Event data containing event_number, duration, timestamp, etc.
        """
        event_number = data.get("event_number")
        duration = data.get("duration")
        doa = data.get("doa")
        angle_degrees = doa.get("angle_degrees")
        angle_radians = doa.get("angle_radians")

        logger.info(f"💭 Processing speech event #{event_number}")
        
        # Create a user message representing the speech event
        # In a real system, this would be transcribed speech
        # For now, we'll create a generic message indicating user spoke
        user_message = f"*Heard from {angle_degrees:.2f}° degrees* " +  f"\"{data.get("transcription", "")}\""
        logger.info(f"User: {user_message}")
        # For a real implementation, you would:
        # 1. Get the audio file saved by hearing_event_emitter
        # 2. Transcribe it using Whisper or similar
        # 3. Use the transcribed text as user_message
                        
        # Process through conversation system
        response = await self.process_message(user_message)
        
        logger.info(f"🤖 Reachy: {response}")
        logger.info(f"✓ Response complete ({self.parser.speech_count()} speech items, {self.parser.action_count()} action items)")
    
    async def chat_completion_stream(
        self,
        messages: List[Dict[str, Any]],
        max_tokens: int = 700
    ):
        """
        Make a streaming chat completion request.
        
        Args:
            messages: Conversation history
            max_tokens: Maximum tokens to generate
            
        Yields:
            Content tokens from the streaming response
        """
        payload = {
            "model": MODEL_NAME,
            "messages": messages,
            "max_tokens": max_tokens,
            "temperature": AGENT_TEMPERATURE,
            "stream": True
        }
                
        async with httpx.AsyncClient(timeout=60.0) as client:
            try:
                async with client.stream("POST", CHAT_COMPLETIONS_URL, json=payload) as response:
                    response.raise_for_status()
                    
                    async for line in response.aiter_lines():
                        if line.startswith("data: "):
                            data_str = line[6:]  # Remove "data: " prefix
                            
                            if data_str == "[DONE]":
                                break
                            
                            try:
                                data = json.loads(data_str)
                                choices = data.get("choices", [])
                                
                                if choices:
                                    delta = choices[0].get("delta", {})
                                    content = delta.get("content", "")
                                    
                                    if content:
                                        yield content
                                        
                            except json.JSONDecodeError:
                                continue
                                
            except httpx.HTTPStatusError as e:
                logger.error(f"HTTP error: {e}")
                logger.error(f"Response: {e.response.text}")
                raise
            except Exception as e:
                logger.error(f"Error during streaming chat completion: {e}")
                raise
    
    async def process_message(self, user_message: str) -> str:
        """
        Process a user message and return the assistant's response.
        
        Args:
            user_message: The user's message text
            
        Returns:
            The assistant's complete response
        """
        # Add user message to conversation
        self.messages.append({"role": "user", "content": user_message})
        
        # Trim history to keep system + last 9 messages (now 10 total with new user message)
        self._trim_conversation_history()
       
        logger.debug(f"Current history: {len(self.messages)} messages")

        # Reset parser state
        self.parser.reset()
        
        # Clear any pending speech when new user input arrives
        if self.speech_handler:
            await self.speech_handler.clear()
        
        # Clear any pending actions when new user input arrives
        if self.action_handler:
            await self.action_handler.clear()
        
        # Collect full response
        full_response = ""
        
        logger.info("🤖 Processing response...")
        
        # Stream the response
        async for token in self.chat_completion_stream(messages=self.messages):
            full_response += token
            # Parse the token for quotes and actions
            self.parser.parse_token(token)
            
            # Process any speech items that were just parsed
            while self.parser.has_speech():
                speech_text = self.parser.get_speech()
                if speech_text and self.speech_handler:
                    logger.info(f'🗣️  Speaking: "{speech_text[:50]}..."' if len(speech_text) > 50 else f'🗣️  Speaking: "{speech_text}"')
                    await self.speech_handler.speak(speech_text)
            
            # Process any action items that were just parsed
            while self.parser.has_action():
                action_text = self.parser.get_action()
                if action_text and self.action_handler:
                    logger.info(f'⚡ Executing action: **{action_text}**')
                    await self.action_handler.execute(action_text)
        
        # Add assistant response to conversation history
        self.messages.append({"role": "assistant", "content": full_response})
        
        logger.info(f"✓ Full response received: {full_response[:50]}")
        # Run warm-up for caching in background
        asyncio.create_task(self._warm_up_for_caching(full_response))
        
        return full_response
    
    async def run(self):
        """Run the conversation application."""
        logger.info("=" * 70)
        logger.info("Conversation Application with Integrated Gateway")
        logger.info("=" * 70)
        logger.info("")
        logger.info("This app will:")
        logger.info("  1. Start Reachy Gateway (daemon + hearing)")
        logger.info("  2. Listen for speech events via callbacks")
        logger.info("  3. Process speech through vLLM streaming chat")
        logger.info("  4. Parse responses into quotes and actions")
        logger.info("=" * 70)
        logger.info("")
    
        # Start gateway in background
        logger.info("Step 1: Starting Reachy Gateway...")
        gateway_task = asyncio.create_task(self.gateway.run())
        logger.info("   ✓ Gateway task started")
        
        logger.info("Step 2: Listening for speech events...")
        logger.info("👂 Ready for voice interaction...")
        logger.info("")
        
        try:
            # Wait for gateway task (runs indefinitely)
            await gateway_task
        except asyncio.CancelledError:
            logger.info("Gateway task cancelled")
        
        logger.warning("Event listener has stopped")
    
    async def cleanup(self):
        """Cleanup resources."""
        logger.info("🧹 Cleaning up...")
        
        if self.speech_handler:
            self.speech_handler.cleanup()
        
        if self.action_handler:
            self.action_handler.cleanup()
        
        if self.gateway:
            logger.info("Stopping gateway...")
            # Turn off robot smoothly before shutting down
            try:
                self.gateway.turn_off_smoothly(part='reachy', duration=2.0)
            except Exception as e:
                logger.error(f"Error turning off robot: {e}")
            
            self.gateway.shutdown_requested = True
            await asyncio.sleep(0.5)  # Give it time to shutdown gracefully
            self.gateway.cleanup()
        
        logger.info("   ✓ Cleanup complete")


async def main():
    """Main function."""
    logger.info("=" * 70)
    logger.info("Starting Conversation Application")
    logger.info("=" * 70)
    logger.info("")
    logger.info("Make sure:")
    logger.info("  - vLLM server is running on http://localhost:8100")
    logger.info("  - Robot is connected via USB")
    logger.info("=" * 70)
    logger.info("")
    
    app = ConversationApp()  # No socket_path needed
    
    # Handle signals
    loop = asyncio.get_running_loop()
    stop_event = asyncio.Event()
    
    def signal_handler():
        logger.info("Signal received, initiating shutdown...")
        stop_event.set()
        
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, signal_handler)
    
    try:
        # Initialize app
        await app.initialize()
        
        # Run conversation app in background
        app_task = asyncio.create_task(app.run())
        
        # Wait for stop signal
        await stop_event.wait()
        
        logger.info("Shutdown signal received, cancelling app task...")
        app_task.cancel()
        try:
            await app_task
        except asyncio.CancelledError:
            pass
            
    except Exception as e:
        logger.error(f"\n❌ Error: {e}")
        traceback.print_exc()
    finally:
        await app.cleanup()
    
    logger.info("\n✅ Done!\n")


if __name__ == "__main__":
    import signal
    asyncio.run(main())
