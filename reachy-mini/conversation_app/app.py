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
from .logger import get_logger
from .tool_loader import load_tool_definitions


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
        
        # Load tool definitions for function calling
        actions_path = Path("/app/conversation_app/actions")
        self.tools = load_tool_definitions(actions_path)
        logger.info(f"Loaded {len(self.tools)} tools for function calling")
        
        # Initialize components
        self.gateway = None  # Will be initialized in initialize()
        self.parser = ConversationParser()
        self.speech_handler = None  # Will be initialized in initialize()
        self.action_handler = None  # Will be initialized in initialize()
        
        # Video frame memory - store recent frame paths
        self.recent_frames = []  # List of recent frame paths
        self.max_frames_in_memory = int(os.getenv('MAX_FRAMES_IN_MEMORY', '10'))
        
        # DOA from most recent speech event (for parameterized actions)
        self.current_doa = None  # Dict with angle_degrees and angle_radians

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
        elif event_type == "video_frame_captured":
            await self.on_video_frame_captured(data)
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
    
    async def on_video_frame_captured(self, data: Dict[str, Any]):
        """
        Callback for video frame captured events.
        
        Args:
            data: Event data containing frame_number, file_path, timestamp, etc.
        """
        frame_number = data.get("frame_number")
        file_path = data.get("file_path")
        total_frames = data.get("total_frames")
        
        logger.info(f"🎥 Video frame captured: #{frame_number} (total: {total_frames}) - {file_path}")
        
        # Store frame path in memory
        self.recent_frames.append(file_path)
        
        # Keep only the most recent frames in memory
        if len(self.recent_frames) > self.max_frames_in_memory:
            self.recent_frames = self.recent_frames[-self.max_frames_in_memory:]
        
        logger.debug(f"Stored frame path in memory. Total frames in memory: {len(self.recent_frames)}")
    
    async def on_speech_stopped(self, data: Dict[str, Any]):
        """
        Callback for speech stopped events - trigger conversation processing.
        
        Args:
            data: Event data containing event_number, duration, timestamp, etc.
        """
        event_number = data.get("event_number")
        duration = data.get("duration")
        doa_average = data.get("doa_average")  # Get the average DOA from speech segment
        
        # Store DOA for action handler to use with "DOA" parameter
        if doa_average:
            self.current_doa = {
                "angle_degrees": doa_average.get("angle_degrees"),
                "angle_radians": doa_average.get("angle_radians")
            }
            angle_degrees = doa_average.get("angle_degrees")
        else:
            # Fallback if no DOA average available
            self.current_doa = None
            angle_degrees = 0.0

        logger.info(f"💭 Processing speech event #{event_number}")
        
        # Convert DOA angle to compass direction
        # DOA angle: 0° = front, 90° = right, -90° = left
        # Map to compass: North = 0°, East = 90°, West = -90°
        doa_compass = self.gateway._degrees_to_compass(angle_degrees)
        
        # Create a user message representing the speech event with compass direction
        user_message = f"*Heard from {doa_compass} ({angle_degrees:.1f}°)* " + f"\"{data.get('transcription', '')}\""
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
        Make a streaming chat completion request with tool calling support.
        
        Args:
            messages: Conversation history
            max_tokens: Maximum tokens to generate
            
        Yields:
            Dictionary with either 'content' (text token) or 'tool_call' (tool call delta)
        """
        payload = {
            "model": MODEL_NAME,
            "messages": messages,
            "max_tokens": max_tokens,
            "temperature": AGENT_TEMPERATURE,
            "stream": True,
            "tools": self.tools,
            "tool_choice": "auto"  # Let model decide when to use tools
        }
        
        logger.debug(f"Sending request with {len(self.tools)} tools")
        logger.debug(f"Tool names: {[t['function']['name'] for t in self.tools]}")
                
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
                                    tool_calls = delta.get("tool_calls", [])
                                    
                                    # Debug logging
                                    if content or tool_calls:
                                        logger.debug(f"Stream delta - content: {repr(content[:30])}, tool_calls: {len(tool_calls)} items")
                                    
                                    # Yield content tokens
                                    if content:
                                        yield {"type": "content", "content": content}
                                    
                                    # Yield tool call deltas
                                    if tool_calls:
                                        yield {"type": "tool_calls", "tool_calls": tool_calls}
                                else:
                                    logger.debug(f"Empty choices in stream data: {data}")
                                        
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
        import time
        audit_logger = get_logger()
        
        # Add user message to conversation
        self.messages.append({"role": "user", "content": user_message})
        
        # Trim history to keep system + last 9 messages (now 10 total with new user message)
        self._trim_conversation_history()
       
        logger.debug(f"Current history: {len(self.messages)} messages")

        # Reset parser state
        self.parser.reset()
        
        # Pass current DOA to action handler for parameterized actions
        if self.action_handler and self.current_doa:
            self.action_handler.set_doa(self.current_doa)
            logger.debug(f"DOA passed to action handler: {self.current_doa['angle_degrees']:.1f}°")
        
        # Clear any pending speech when new user input arrives
        if self.speech_handler:
            await self.speech_handler.clear()
        
        # Clear any pending actions when new user input arrives
        if self.action_handler:
            await self.action_handler.clear()
        
        # Audit log: model request sent
        audit_logger.log_model_request_sent(
            messages=self.messages,
            parameters={"max_tokens": 700, "temperature": AGENT_TEMPERATURE}
        )
        
        # Collect full response and tool calls
        full_response = ""
        tool_calls_accumulated = {}  # Track tool calls by index
        response_started = False
        response_start_time = time.time()
        
        logger.info("🤖 Processing response...")
        logger.debug(f"Request includes {len(self.tools)} tools")
        
        
        # Stream the response
        async for chunk in self.chat_completion_stream(messages=self.messages):
            # Audit log: response started (first chunk only)
            if not response_started:
                audit_logger.log_model_response_started()
                response_started = True
            
            chunk_type = chunk.get("type")
            
            if chunk_type == "content":
                # Handle content (speech)
                token = chunk.get("content", "")
                full_response += token
                logger.debug(f"Content token: {repr(token[:50])}")
                
                # Parse the token for quotes (speech only now, no actions)
                self.parser.parse_token(token)
                
                # Process any speech items that were just parsed
                while self.parser.has_speech():
                    speech_text = self.parser.get_speech()
                    if speech_text and self.speech_handler:
                        logger.info(f'🗣️  Speaking: "{speech_text[:50]}..."' if len(speech_text) > 50 else f'🗣️  Speaking: "{speech_text}"')
                        # Audit log: parser cut (speech)
                        audit_logger.log_parser_cut("speech", speech_text)
                        await self.speech_handler.speak(speech_text)
            
            elif chunk_type == "tool_calls":
                # Handle tool call deltas
                tool_call_deltas = chunk.get("tool_calls", [])
                logger.debug(f"Tool call deltas: {tool_call_deltas}")
                
                for tc_delta in tool_call_deltas:
                    index = tc_delta.get("index", 0)
                    
                    # Initialize tool call accumulator if needed
                    if index not in tool_calls_accumulated:
                        tool_calls_accumulated[index] = {
                            "id": "",
                            "type": "function",
                            "function": {
                                "name": "",
                                "arguments": ""
                            }
                        }
                    
                    # Accumulate tool call data
                    if "id" in tc_delta:
                        tool_calls_accumulated[index]["id"] = tc_delta["id"]
                    
                    if "function" in tc_delta:
                        func_delta = tc_delta["function"]
                        if "name" in func_delta:
                            tool_calls_accumulated[index]["function"]["name"] += func_delta["name"]
                        if "arguments" in func_delta:
                            tool_calls_accumulated[index]["function"]["arguments"] += func_delta["arguments"]
        
        # Execute accumulated tool calls
        if tool_calls_accumulated:
            logger.info(f"🔧 Executing {len(tool_calls_accumulated)} tool call(s)...")
            for index in sorted(tool_calls_accumulated.keys()):
                tool_call = tool_calls_accumulated[index]
                tool_name = tool_call["function"]["name"]
                tool_args_str = tool_call["function"]["arguments"]
                
                try:
                    # Parse arguments JSON
                    tool_args = json.loads(tool_args_str) if tool_args_str else {}
                except json.JSONDecodeError as e:
                    logger.error(f"Failed to parse tool arguments: {e}")
                    logger.error(f"Arguments string: {tool_args_str}")
                    continue
                
                logger.info(f"⚡ Executing tool: {tool_name} with args: {tool_args}")
                
                # Audit log: tool call execution
                audit_logger.log_tool_call_executed(tool_name, tool_args)
                
                # Execute tool via action_handler
                if self.action_handler:
                    # Call new execute_tool method that accepts structured commands
                    await self.action_handler.execute_tool(tool_name, tool_args)
        else:
            logger.info("No tool calls in response")
        
        # Audit log: model response finished
        response_latency_ms = (time.time() - response_start_time) * 1000
        audit_logger.log_model_response_finished(full_response, response_latency_ms)
        
        # Log summary of what was received
        logger.info(f"✅ Response complete: {len(full_response)} chars, {len(tool_calls_accumulated)} tool calls, {response_latency_ms:.0f}ms")
        if not full_response and not tool_calls_accumulated:
            logger.warning("⚠️  Model returned empty response (no content and no tool calls)")
        
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
            #try:
            #    self.gateway.turn_off_smoothly()
            #except Exception as e:
            #    logger.error(f"Error turning off robot: {e}")
            
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
