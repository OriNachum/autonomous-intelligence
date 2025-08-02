"""Main coordination loop for Gemma"""

import asyncio
import logging
import time
from typing import Dict, Any, Optional, List
import numpy as np

from .model_interface import ModelInterface
from .response_processor import ResponseProcessor
from ..event_system import EventConsumer, EventManager, EventType, GemmaEvent
from ..memory_system import MemoryManager
from ..config import Config

class MainLoop:
    """Main coordination loop that handles events and model inference"""
    
    def __init__(self, config: Config):
        self.config = config
        self.logger = logging.getLogger(__name__)
        
        # Core components
        self.model_interface = ModelInterface(config)
        self.response_processor = ResponseProcessor(config)
        self.memory_manager = MemoryManager(config)
        self.event_consumer = EventConsumer(config, "main_loop")
        
        # Processing state
        self.running = False
        self.processing_active = False
        
        # Current multimodal input
        self.current_text = None
        self.current_image = None
        self.current_audio = None
        self.current_context = {}
        
        # Event handling
        self.pending_events = []
        self.last_processing_time = 0
        self.processing_cooldown = 0.1  # seconds
        
        # Performance tracking
        self.total_inferences = 0
        self.total_processing_time = 0
        self.response_times = []
        
        # State tracking
        self.wake_word_active = False
        self.speech_active = False
        self.last_camera_frame = None
        self.last_camera_time = 0
        
        # Register event handlers
        self._register_event_handlers()
    
    def _register_event_handlers(self):
        """Register event handlers"""
        self.event_consumer.register_handler(EventType.TEXT_INPUT, self._handle_text_input)
        self.event_consumer.register_handler(EventType.CAMERA_FRAME, self._handle_camera_frame)
        self.event_consumer.register_handler(EventType.SPEECH_DETECTED, self._handle_speech_detected)
        self.event_consumer.register_handler(EventType.WAKE_WORD_DETECTED, self._handle_wake_word_detected)
        self.event_consumer.register_handler(EventType.OBJECT_DETECTED, self._handle_object_detected)
        self.event_consumer.register_handler(EventType.OBJECT_DISAPPEARED, self._handle_object_disappeared)
        self.event_consumer.register_handler(EventType.RESET_QUEUE, self._handle_reset)
        self.event_consumer.register_handler(EventType.SYSTEM_SHUTDOWN, self._handle_shutdown)
    
    async def start(self):
        """Start the main loop"""
        self.logger.info("Starting main loop")
        
        # Connect components
        await self.event_consumer.connect()
        await self.response_processor.connect()
        await self.memory_manager.start()
        
        # Start consuming events
        await self.event_consumer.start_consuming()
        
        self.running = True
        self.processing_active = True
        
        # Start processing loop
        asyncio.create_task(self._processing_loop())
        
        self.logger.info("Main loop started")
    
    async def stop(self):
        """Stop the main loop"""
        self.logger.info("Stopping main loop")
        
        self.running = False
        self.processing_active = False
        
        # Disconnect components
        await self.event_consumer.stop_consuming()
        await self.response_processor.disconnect()
        await self.memory_manager.stop()
        await self.model_interface.cleanup()
        
        self.logger.info("Main loop stopped")
    
    async def _processing_loop(self):
        """Main processing loop"""
        while self.processing_active:
            try:
                # Check for pending events
                if self.pending_events:
                    await self._process_pending_events()
                
                # Check if we should trigger inference
                if self._should_trigger_inference():
                    await self._trigger_inference()
                
                await asyncio.sleep(0.01)  # Small delay to prevent busy waiting
                
            except Exception as e:
                self.logger.error(f"Error in processing loop: {e}")
                await asyncio.sleep(0.1)
    
    async def _process_pending_events(self):
        """Process pending events"""
        # Sort events by priority and timestamp
        self.pending_events.sort(key=lambda x: (-x.priority, x.timestamp))
        
        # Process high priority events immediately
        high_priority_events = [e for e in self.pending_events if e.priority > 0]
        
        if high_priority_events:
            # Process immediately
            await self._process_event_batch(high_priority_events)
            self.pending_events = [e for e in self.pending_events if e.priority <= 0]
        
        # Process regular events if cooldown has passed
        elif time.time() - self.last_processing_time > self.processing_cooldown:
            await self._process_event_batch(self.pending_events)
            self.pending_events = []
    
    async def _process_event_batch(self, events: List[GemmaEvent]):
        """Process a batch of events"""
        if not events:
            return
        
        # Update current state based on events
        self._update_current_state(events)
        
        # Mark as processed
        self.last_processing_time = time.time()
        
        self.logger.debug(f"Processed {len(events)} events")
    
    def _update_current_state(self, events: List[GemmaEvent]):
        """Update current multimodal state based on events"""
        for event in events:
            if event.event_type == EventType.TEXT_INPUT:
                self.current_text = event.data.get('text')
                self.current_context['text_timestamp'] = event.timestamp
                
            elif event.event_type == EventType.CAMERA_FRAME:
                self.current_image = event.data.get('frame_data')
                self.current_context['camera_timestamp'] = event.timestamp
                self.current_context['detections'] = event.data.get('detections', [])
                
            elif event.event_type == EventType.SPEECH_DETECTED:
                self.current_audio = event.data.get('audio_data')
                self.current_context['audio_timestamp'] = event.timestamp
                self.current_context['speech_confidence'] = event.data.get('confidence', 0)
                
            elif event.event_type == EventType.WAKE_WORD_DETECTED:
                self.wake_word_active = True
                self.current_context['wake_word'] = event.data.get('wake_word')
                self.current_context['wake_word_timestamp'] = event.timestamp
                
            elif event.event_type in [EventType.OBJECT_DETECTED, EventType.OBJECT_DISAPPEARED]:
                # Add to context
                if 'object_events' not in self.current_context:
                    self.current_context['object_events'] = []
                self.current_context['object_events'].append({
                    'type': event.event_type.value,
                    'detections': event.data.get('detections', []),
                    'timestamp': event.timestamp
                })
    
    def _should_trigger_inference(self) -> bool:
        """Determine if we should trigger model inference"""
        # Trigger on text input
        if self.current_text:
            return True
        
        # Trigger on wake word
        if self.wake_word_active:
            return True
        
        # Trigger on significant object changes
        if 'object_events' in self.current_context:
            recent_events = [e for e in self.current_context['object_events'] 
                           if time.time() - e['timestamp'] < 5.0]
            if recent_events:
                return True
        
        return False
    
    async def _trigger_inference(self):
        """Trigger model inference with current multimodal input"""
        try:
            start_time = time.time()
            
            # Prepare context
            context = self.current_context.copy()
            context['wake_word_active'] = self.wake_word_active
            context['speech_active'] = self.speech_active
            
            # Get memory context if we have text input
            if self.current_text:
                memory_context = await self.memory_manager.get_memory_context(self.current_text, context)
                context.update(memory_context)
            
            # Generate response
            response = await self.model_interface.process_multimodal_input(
                text_input=self.current_text,
                image_data=self.current_image,
                audio_data=self.current_audio,
                context=context
            )
            
            # Process response
            await self.response_processor.process_response(response, context)
            
            # Process conversation for memory
            if self.current_text:
                await self.memory_manager.process_conversation(
                    self.current_text, response, context
                )
            
            # Update statistics
            inference_time = time.time() - start_time
            self.total_inferences += 1
            self.total_processing_time += inference_time
            self.response_times.append(inference_time)
            
            if len(self.response_times) > 100:
                self.response_times.pop(0)
            
            self.logger.info(f"Inference completed in {inference_time:.2f}s")
            
            # Reset state
            self._reset_current_state()
            
        except Exception as e:
            self.logger.error(f"Error in inference: {e}")
            self._reset_current_state()
    
    def _reset_current_state(self):
        """Reset current multimodal state after processing"""
        self.current_text = None
        self.current_audio = None
        # Keep image for context but mark as processed
        self.current_context.pop('text_timestamp', None)
        self.current_context.pop('audio_timestamp', None)
        self.current_context.pop('object_events', None)
        self.wake_word_active = False
        self.speech_active = False
    
    # Event handlers
    async def _handle_text_input(self, event: GemmaEvent):
        """Handle text input event"""
        self.pending_events.append(event)
        event.priority = 1  # High priority
        
    async def _handle_camera_frame(self, event: GemmaEvent):
        """Handle camera frame event"""
        self.pending_events.append(event)
        event.priority = 0  # Normal priority
        
    async def _handle_speech_detected(self, event: GemmaEvent):
        """Handle speech detection event"""
        self.speech_active = True
        self.pending_events.append(event)
        event.priority = 1  # High priority
        
    async def _handle_wake_word_detected(self, event: GemmaEvent):
        """Handle wake word detection event"""
        self.pending_events.append(event)
        event.priority = 2  # Highest priority
        
    async def _handle_object_detected(self, event: GemmaEvent):
        """Handle object detection event"""
        self.pending_events.append(event)
        event.priority = 0  # Normal priority
        
    async def _handle_object_disappeared(self, event: GemmaEvent):
        """Handle object disappearance event"""
        self.pending_events.append(event)
        event.priority = 0  # Normal priority
        
    async def _handle_reset(self, event: GemmaEvent):
        """Handle reset event"""
        self.logger.info("Resetting main loop state")
        self._reset_current_state()
        self.pending_events = []
        
        # Clear conversation history
        self.model_interface.clear_conversation_history()
        self.response_processor.clear_history()
        await self.memory_manager.clear_memory()
        
    async def _handle_shutdown(self, event: GemmaEvent):
        """Handle shutdown event"""
        self.logger.info("Shutdown requested")
        await self.stop()
    
    def get_status(self) -> Dict[str, Any]:
        """Get main loop status"""
        avg_response_time = (sum(self.response_times) / len(self.response_times) 
                           if self.response_times else 0)
        
        return {
            'running': self.running,
            'processing_active': self.processing_active,
            'total_inferences': self.total_inferences,
            'total_processing_time': self.total_processing_time,
            'avg_response_time': avg_response_time,
            'pending_events': len(self.pending_events),
            'wake_word_active': self.wake_word_active,
            'speech_active': self.speech_active,
            'last_processing_time': self.last_processing_time,
            'current_state': {
                'has_text': self.current_text is not None,
                'has_image': self.current_image is not None,
                'has_audio': self.current_audio is not None,
                'context_keys': list(self.current_context.keys())
            },
            'model_stats': self.model_interface.get_statistics(),
            'response_stats': self.response_processor.get_statistics(),
            'memory_stats': self.memory_manager.get_statistics()
        }