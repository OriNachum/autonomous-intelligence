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
from .movement_manager import MovementManager


# Set up logging
logging.basicConfig(
    level=logging.ERROR,  # Changed to DEBUG for detailed logging
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Configuration
CHAT_COMPLETIONS_URL = os.environ.get("VLLM_FRONT_URL", "http://localhost:8100/v1/chat/completions")
MODEL_NAME = os.environ.get("MODEL_ID", "RedHatAI/Llama-3.2-3B-Instruct-FP8")
AGENT_TEMPERATURE = 0.7

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
        self.movement_manager = None  # Will be initialized in initialize()
        
        # Video frame memory - store recent frame paths
        self.recent_frames = []  # List of recent frame paths
        self.max_frames_in_memory = int(os.getenv('MAX_FRAMES_IN_MEMORY', '10'))
        
        # DOA from most recent speech event (for parameterized actions)
        self.current_doa = None  # Dict with angle_degrees and angle_radians
        
        # Vision context - latest stable vision information
        self.latest_vision_context = None  # Dict with {'objects': [...], 'faces': [...], 'timestamp': int}
        
        # Conversation audit logging
        self.audit_log_path = None

    async def initialize(self):
        """Initialize the application."""
        logger.info("=" * 70)
        logger.info("Initializing Conversation App")
        logger.info("=" * 70)
        
        # Initialize conversation with system prompt
        self.messages = [
            {"role": "system", "content": self.system_prompt}
        ]
        
        # Create conversation audit log file
        try:
            from datetime import datetime
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            log_filename = f"conversation.{timestamp}.log"
            logs_dir = Path("/app/conversation_app/logs")
            logs_dir.mkdir(parents=True, exist_ok=True)
            self.audit_log_path = logs_dir / log_filename
            
            # Write system prompt to audit log
            self._write_audit_log("--- SYSTEM PROMPT ---", self.system_prompt)
            logger.info(f"✓ Conversation audit log created: {self.audit_log_path}")
        except Exception as e:
            logger.error(f"❌ Failed to create conversation audit log: {e}")
            self.audit_log_path = None
        
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
            self.action_handler = ActionHandler(
                gateway=self.gateway,
                event_callback=self.on_action_event,
                tts_queue=self.speech_handler.tts_queue if self.speech_handler else None
            )
            # Warm up action handler in background
            #asyncio.create_task(self.action_handler.execute("nod head"))

            logger.info("✓ Action handler initialized")
        except Exception as e:
            logger.error(f"❌ Failed to initialize action handler: {e}")
            logger.warning("   Continuing without action execution...")
            self.action_handler = None
        
        # Initialize movement manager
        try:
            self.movement_manager = MovementManager(
                reachy_controller=self.gateway.reachy_controller
            )
            
            # Link movement manager to controller (enables non-blocking move_smoothly_to)
            self.gateway.reachy_controller.movement_manager = self.movement_manager
            
            self.movement_manager.start()
            # Start with idle animations enabled (antenna wiggling while waiting)
            self.movement_manager.enable_idle(True)
            logger.info("✓ Movement manager initialized and started with idle animations")
        except Exception as e:
            logger.error(f"❌ Failed to initialize movement manager: {e}")
            logger.warning("   Continuing without background movements...")
            self.movement_manager = None
        
        logger.info("✓ App initialized")
        logger.info("=" * 70)
    
    def _write_audit_log(self, header: str, content: str):
        """Write an entry to the conversation audit log."""
        if not self.audit_log_path:
            return
        
        try:
            with open(self.audit_log_path, 'a', encoding='utf-8') as f:
                f.write(f"\n{header}\n")
                f.write(f"{content}\n")
                f.write("-" * len(header) + "\n")
        except Exception as e:
            logger.error(f"Failed to write to audit log: {e}")
    
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
        logger.debug(f"Gateway event: {event_type}")
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
        elif event_type == "yolo_v8_result":
            await self.on_vision_result(data)
        elif event_type == "face_recognition_result":
            await self.on_vision_result(data)
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


    async def on_action_event(self, event_type: str, data: Dict[str, Any]):
        """
        Handle action execution events for model context update.
        
        This callback is invoked from the actions queue background thread,
        so we need to be thread-safe when updating conversation history.
        
        Args:
            event_type: Type of event (action_started, action_completed, action_failed)
            data: Event data
        """
        import asyncio
        import threading
        
        # Get the current event loop (main loop)
        try:
            main_loop = asyncio.get_event_loop()
        except RuntimeError:
            logger.warning("No event loop available for action event callback")
            return
        
        # Define async handler for event
        async def handle_event():
            if event_type == "action_started":
                action = data.get("action")
                logger.info(f"📍 Action started: {action}")
            
            elif event_type == "action_completed":
                action = data.get("action")
                result = data.get("result", {})
                
                # Don't add system messages - tool results are now added as 'tool' role messages in process_message
                if action != "speak":
                    logger.info(f"✅ Action completed: {action}")
                else:
                    logger.info(f"✅ Speech completed: {result.get('text', '')[:50]}...")
            
            elif event_type == "action_failed":
                action = data.get("action")
                error = data.get("error", "Unknown error")
                
                # Don't add system messages - tool errors are logged in audit trail
                logger.error(f"❌ Action failed: {action} - {error}")
        
        # Schedule the async handler on the main event loop
        if threading.current_thread() != threading.main_thread():
            # Called from background thread - schedule on main loop
            asyncio.run_coroutine_threadsafe(handle_event(), main_loop)
        else:
            # Already on main thread - can run directly
            await handle_event()
    
    async def on_speech_started(self, data: Dict[str, Any]):
        """
        Callback for speech started events.
        
        Args:
            data: Event data containing event_number, timestamp, etc.
        """
        # Enable idle animations when user speaks (antennas moving)
        if self.movement_manager:
            self.movement_manager.enable_idle(True)
            logger.debug("Idle animations: enabled (user speaking)")
        
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
    
    async def on_vision_result(self, data: Dict[str, Any]):
        """
        Callback for vision processor result events (YOLO, face recognition, etc.).
        
        Args:
            data: Event data containing processor results
        """
        timestamp = data.get("timestamp")
        stable_labels = data.get("stable_labels", [])
        
        # Initialize vision context if needed
        if self.latest_vision_context is None:
            self.latest_vision_context = {
                'objects': [],
                'faces': [],
                'timestamp': timestamp
            }
        
        # Update vision context based on stable labels
        objects = []
        faces = []
        
        for label in stable_labels:
            if label.startswith("person:"):
                # Face recognition result
                name = label.split(":", 1)[1]
                faces.append(name)
            else:
                # Object detection result
                objects.append(label)
        
        # Update context
        self.latest_vision_context['objects'] = objects
        self.latest_vision_context['faces'] = faces
        self.latest_vision_context['timestamp'] = timestamp
        
        # Log the update
        context_items = []
        if objects:
            context_items.append(f"objects: {', '.join(objects)}")
        if faces:
            context_items.append(f"faces: {', '.join(faces)}")
        
        if context_items:
            logger.info(f"👁️  Vision context updated: {' | '.join(context_items)}")
        else:
            logger.info(f"👁️  Vision context cleared (no stable detections)")
    
    
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
        
        # Add visual context if available and recent (within 5 seconds)
        import time
        current_time = int(time.time() * 1000)  # Current time in milliseconds
        if self.latest_vision_context and self.latest_vision_context.get('timestamp'):
            vision_age_ms = current_time - self.latest_vision_context['timestamp']
            vision_age_seconds = vision_age_ms / 1000.0
            
            if vision_age_seconds < 5.0:  # Vision context is recent enough
                vision_items = []
                
                # Add objects to visual context
                objects = self.latest_vision_context.get('objects', [])
                if objects:
                    vision_items.extend(objects)
                
                # Add faces to visual context
                faces = self.latest_vision_context.get('faces', [])
                if faces:
                    for face in faces:
                        if face != 'unknown':
                            vision_items.append(face)
                        else:
                            vision_items.append('an unknown person')
                
                # Append visual context to user message
                if vision_items:
                    visual_context_str = ', '.join(vision_items)
                    user_message += f" *[Visual Context: You see {visual_context_str}]*"
                    logger.info(f"🔍 Added visual context: {visual_context_str}")
            else:
                logger.debug(f"Vision context too old ({vision_age_seconds:.1f}s), skipping")
        
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
        max_tokens: int = 2000
    ):
        """
        Make a streaming chat completion request with tool calling support.
        
        Args:
            messages: Conversation history
            max_tokens: Maximum tokens to generate
            
        Yields:
            Dictionary with either 'content' (text token) or 'tool_call' (tool call delta)
        """
        # Filter out 'tool' role messages for vLLM compatibility
        # Many vLLM deployments don't support tool role in conversation history
        # We keep them in our internal history but strip them when sending to API
        filtered_messages = [
            msg for msg in messages 
            if msg.get("role") != "tool"
        ]
        
        # Debug: log if we filtered any messages
        if len(filtered_messages) < len(messages):
            logger.debug(f"Filtered {len(messages) - len(filtered_messages)} tool messages from API request")
        
        payload = {
            "model": MODEL_NAME,
            "messages": filtered_messages,
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
                # For streaming responses, need to read body first
                try:
                    error_body = await e.response.aread()
                    logger.error(f"Response: {error_body.decode('utf-8')}")
                except Exception as read_error:
                    logger.error(f"Could not read error response: {read_error}")
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
        user_msg = {"role": "user", "content": user_message}
        self.messages.append(user_msg)
        
        # Write user message to audit log
        self._write_audit_log("--- USER REQUEST ---", json.dumps(user_msg, indent=2))
        
        # Trim history to keep system + last 9 messages (now 10 total with new user message)
        self._trim_conversation_history()
       
        logger.debug(f"Current history: {len(self.messages)} messages")

        # Reset parser state
        self.parser.reset()
        
        # Pass current DOA to action handler for parameterized actions
        if self.action_handler and self.current_doa:
            self.action_handler.set_doa(self.current_doa)
            logger.debug(f"DOA passed to action handler: {self.current_doa['angle_degrees']:.1f}°")
        
        # Disable idle animations while robot speaks/acts
        if self.movement_manager:
            self.movement_manager.enable_idle(False)
            logger.debug("Idle animations: disabled (robot responding)")
        
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
        is_json_response = False  # Flag to detect JSON responses
        
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
                
                # Detect JSON early (first content token that starts with {)
                if not is_json_response and full_response.strip().startswith('{'):
                    is_json_response = True
                    logger.debug("Detected JSON response format")
                
                # Only use ConversationParser for non-JSON responses
                if not is_json_response:
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
        tool_results = {}  # Store results by tool_call_id
        if tool_calls_accumulated:
            logger.info(f"🔧 Executing {len(tool_calls_accumulated)} tool call(s)...")
            for index in sorted(tool_calls_accumulated.keys()):
                tool_call = tool_calls_accumulated[index]
                tool_name = tool_call["function"]["name"]
                tool_args_str = tool_call["function"]["arguments"]
                tool_call_id = tool_call["id"]
                
                try:
                    # Parse arguments JSON (DO NOT append to full_response)
                    tool_args = json.loads(tool_args_str) if tool_args_str else {}
                except json.JSONDecodeError as e:
                    logger.error(f"Failed to parse tool arguments: {e}")
                    logger.error(f"Arguments string: {tool_args_str}")
                    continue
                
                logger.info(f"⚡ Executing tool: {tool_name} with args: {tool_args}")
                
                # Audit log: tool call execution
                audit_logger.log_tool_call_executed(tool_name, tool_args)
                
                # Measure tool execution time
                tool_start_time = time.time()
                tool_success = True
                tool_error = None
                tool_result = None
                
                # Execute tool via action_handler
                if self.action_handler:
                    try:
                        # Call execute_tool method that accepts structured commands
                        tool_result = await self.action_handler.execute_tool(tool_name, tool_args)
                        logger.info(f"✅ Tool {tool_name} executed successfully")
                    except Exception as e:
                        tool_success = False
                        tool_error = str(e)
                        logger.error(f"❌ Tool {tool_name} failed: {e}")
                        tool_result = {"error": tool_error}
                
                # Calculate execution time
                tool_duration_ms = (time.time() - tool_start_time) * 1000
                
                # Audit log: tool output
                audit_logger.log_tool_output(
                    tool_name=tool_name,
                    tool_call_id=tool_call_id,
                    output=tool_result,
                    duration_ms=tool_duration_ms,
                    success=tool_success,
                    error=tool_error
                )
                
                # Store result for history
                tool_results[tool_call_id] = {
                    "result": tool_result,
                    "success": tool_success,
                    "error": tool_error
                }
        else:
            logger.info("No tool calls in response")
        
        # Handle JSON responses: extract and queue speech field
        if is_json_response and full_response.strip():
            try:
                response_json = json.loads(full_response.strip())
                speech_text = response_json.get('speech', '')
                if speech_text and self.speech_handler:
                    logger.info(f'🗣️  Speaking (from JSON): "{speech_text[:50]}..."' if len(speech_text) > 50 else f'🗣️  Speaking (from JSON): "{speech_text}"')
                    # Audit log: parser cut (speech from JSON)
                    audit_logger.log_parser_cut("speech", speech_text)
                    await self.speech_handler.speak(speech_text)
                elif not speech_text:
                    logger.debug("JSON response has no 'speech' field")
            except json.JSONDecodeError as e:
                logger.warning(f"Response looked like JSON but failed to parse: {e}")
                logger.debug(f"Response content: {full_response[:100]}...")
                # ConversationParser already handled it during streaming (if not JSON)
                # If it was detected as JSON but invalid, we may have lost speech - log warning
                if is_json_response:
                    logger.warning("⚠️  Invalid JSON response detected - speech may have been lost!")
        
        # Audit log: model response finished
        response_latency_ms = (time.time() - response_start_time) * 1000
        audit_logger.log_model_response_finished(full_response, response_latency_ms)
        
        # Log summary of what was received
        logger.info(f"✅ Response complete: {len(full_response)} chars, {len(tool_calls_accumulated)} tool calls, {response_latency_ms:.0f}ms")
        if not full_response and not tool_calls_accumulated:
            logger.warning("⚠️  Model returned empty response (no content and no tool calls)")
        
        # Add assistant response to conversation history with proper tool_calls field
        assistant_msg = {
            "role": "assistant",
            "content": full_response if full_response else None
        }
        
        # Add tool_calls field if there were any tool calls
        if tool_calls_accumulated:
            assistant_msg["tool_calls"] = [
                {
                    "id": tool_calls_accumulated[index]["id"],
                    "type": "function",
                    "function": {
                        "name": tool_calls_accumulated[index]["function"]["name"],
                        "arguments": tool_calls_accumulated[index]["function"]["arguments"]
                    }
                }
                for index in sorted(tool_calls_accumulated.keys())
            ]
        
        self.messages.append(assistant_msg)
        
        # Write assistant message to audit log
        self._write_audit_log("--- MODEL RESPONSE ---", json.dumps(assistant_msg, indent=2))
        
        # Add tool response messages using 'tool' role (standard format)
        for tool_call_id, result_data in tool_results.items():
            tool_response_msg = {
                "role": "tool",
                "tool_call_id": tool_call_id,
                "content": json.dumps(result_data["result"]) if result_data["result"] else json.dumps({"status": "completed"})
            }
            self.messages.append(tool_response_msg)
            logger.debug(f"Added tool response to history for tool_call_id: {tool_call_id}")
        
        logger.info(f"✓ Full response received: {full_response[:50]}")
        # Run warm-up for caching in background
        asyncio.create_task(self._warm_up_for_caching(full_response))
        
        # Return to WAITING mode after robot finishes speaking/acting
        if self.movement_manager:
            # Re-enable idle animations after response complete
            self.movement_manager.enable_idle(True)
            logger.debug("Movement mode: WAITING (response complete)")
        
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
        
        # Set STATIC mode before shutdown to prevent antenna interference
        if self.movement_manager:
            logger.info("Disabling idle animations for shutdown...")
            self.movement_manager.enable_idle(False)
            # Give time for any in-flight antenna updates to complete
            await asyncio.sleep(0.1)
            self.movement_manager.cleanup()
        
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
