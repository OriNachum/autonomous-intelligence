"""Response processor for handling model outputs"""

import logging
import re
from typing import List, Dict, Any, Optional, Tuple
import time

from ..event_system import EventProducer, EventType, TTSEvent
from ..config import Config

class ResponseProcessor:
    """Processes model responses and handles TTS, actions, and memory"""
    
    def __init__(self, config: Config):
        self.config = config
        self.logger = logging.getLogger(__name__)
        
        # Event system
        self.event_producer = EventProducer(config, "response_processor")
        
        # Response patterns
        self.quoted_pattern = re.compile(r'"([^"]*)"')
        self.action_pattern = re.compile(r'\*([^*]*)\*')
        self.memory_pattern = re.compile(r'\[MEMORY:([^\]]*)\]')
        
        # Processing statistics
        self.processed_responses = 0
        self.total_sentences = 0
        self.total_actions = 0
        self.total_memory_items = 0
        
        # Response history
        self.response_history: List[Dict[str, Any]] = []
        self.max_history = 50
    
    async def connect(self):
        """Connect to event system"""
        await self.event_producer.connect()
    
    async def disconnect(self):
        """Disconnect from event system"""
        await self.event_producer.disconnect()
    
    async def process_response(self, response: str, context: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Process a model response and extract components"""
        start_time = time.time()
        
        try:
            # Parse response components
            components = self._parse_response(response)
            
            # Process each component type
            await self._process_tts_sentences(components['sentences'])
            await self._process_actions(components['actions'])
            await self._process_memory_items(components['memory_items'])
            
            # Create processing result
            result = {
                'original_response': response,
                'components': components,
                'processing_time': time.time() - start_time,
                'timestamp': time.time(),
                'context': context or {}
            }
            
            # Update statistics
            self._update_statistics(components)
            
            # Add to history
            self._add_to_history(result)
            
            self.logger.debug(f"Processed response with {len(components['sentences'])} sentences, "
                            f"{len(components['actions'])} actions, "
                            f"{len(components['memory_items'])} memory items")
            
            return result
            
        except Exception as e:
            self.logger.error(f"Error processing response: {e}")
            return {
                'original_response': response,
                'components': {'sentences': [], 'actions': [], 'memory_items': [], 'plain_text': response},
                'processing_time': time.time() - start_time,
                'timestamp': time.time(),
                'context': context or {},
                'error': str(e)
            }
    
    def _parse_response(self, response: str) -> Dict[str, Any]:
        """Parse response into components"""
        components = {
            'sentences': [],
            'actions': [],
            'memory_items': [],
            'plain_text': response
        }
        
        # Extract quoted sentences (for TTS)
        quoted_matches = self.quoted_pattern.findall(response)
        components['sentences'] = [sentence.strip() for sentence in quoted_matches if sentence.strip()]
        
        # Extract actions (marked with asterisks)
        action_matches = self.action_pattern.findall(response)
        components['actions'] = [action.strip() for action in action_matches if action.strip()]
        
        # Extract memory items (marked with [MEMORY:...])
        memory_matches = self.memory_pattern.findall(response)
        components['memory_items'] = [item.strip() for item in memory_matches if item.strip()]
        
        return components
    
    async def _process_tts_sentences(self, sentences: List[str]):
        """Process sentences for TTS"""
        if not sentences:
            return
        
        try:
            # Filter out empty sentences
            valid_sentences = [s for s in sentences if s.strip()]
            
            if valid_sentences:
                # Send TTS event
                tts_event = TTSEvent(
                    event_type=EventType.QUEUE_SENTENCES,
                    sentences=valid_sentences
                )
                await self.event_producer.send_event(tts_event)
                
                self.logger.debug(f"Queued {len(valid_sentences)} sentences for TTS")
                
        except Exception as e:
            self.logger.error(f"Error processing TTS sentences: {e}")
    
    async def _process_actions(self, actions: List[str]):
        """Process actions (placeholder for future robotic control)"""
        if not actions:
            return
        
        try:
            for action in actions:
                # Log action for now
                self.logger.info(f"Action: {action}")
                
                # Future: Send action events to robotic control system
                # action_event = ActionEvent(
                #     event_type=EventType.ACTION_REQUESTED,
                #     action=action
                # )
                # await self.event_producer.send_event(action_event)
                
        except Exception as e:
            self.logger.error(f"Error processing actions: {e}")
    
    async def _process_memory_items(self, memory_items: List[str]):
        """Process memory items for fact distillation"""
        if not memory_items:
            return
        
        try:
            for item in memory_items:
                # Log memory item for now
                self.logger.debug(f"Memory item: {item}")
                
                # Future: Send to memory system
                # memory_event = MemoryEvent(
                #     event_type=EventType.FACT_DISTILLED,
                #     fact=item
                # )
                # await self.event_producer.send_event(memory_event)
                
        except Exception as e:
            self.logger.error(f"Error processing memory items: {e}")
    
    def _update_statistics(self, components: Dict[str, Any]):
        """Update processing statistics"""
        self.processed_responses += 1
        self.total_sentences += len(components['sentences'])
        self.total_actions += len(components['actions'])
        self.total_memory_items += len(components['memory_items'])
    
    def _add_to_history(self, result: Dict[str, Any]):
        """Add processing result to history"""
        self.response_history.append(result)
        
        # Trim history
        if len(self.response_history) > self.max_history:
            self.response_history.pop(0)
    
    def extract_sentences_for_streaming(self, partial_response: str) -> List[str]:
        """Extract complete sentences from partial response for streaming"""
        # Find complete quoted sentences
        complete_sentences = []
        
        # Look for complete quoted sentences
        matches = self.quoted_pattern.findall(partial_response)
        for match in matches:
            sentence = match.strip()
            if sentence and sentence.endswith(('.', '!', '?')):
                complete_sentences.append(sentence)
        
        return complete_sentences
    
    def is_response_complete(self, response: str) -> bool:
        """Check if response appears to be complete"""
        # Simple heuristics for response completion
        response = response.strip()
        
        if not response:
            return False
        
        # Check if ends with proper punctuation
        if response.endswith(('.', '!', '?')):
            return True
        
        # Check if ends with a complete quoted sentence
        quoted_matches = self.quoted_pattern.findall(response)
        if quoted_matches:
            last_quote = quoted_matches[-1].strip()
            if last_quote.endswith(('.', '!', '?')):
                return True
        
        return False
    
    def clean_response(self, response: str) -> str:
        """Clean up response text"""
        # Remove extra whitespace
        response = re.sub(r'\s+', ' ', response)
        
        # Remove incomplete sentences at the end
        # This is a simple implementation
        response = response.strip()
        
        return response
    
    def get_statistics(self) -> Dict[str, Any]:
        """Get processing statistics"""
        return {
            'processed_responses': self.processed_responses,
            'total_sentences': self.total_sentences,
            'total_actions': self.total_actions,
            'total_memory_items': self.total_memory_items,
            'avg_sentences_per_response': (self.total_sentences / self.processed_responses 
                                         if self.processed_responses > 0 else 0),
            'avg_actions_per_response': (self.total_actions / self.processed_responses 
                                       if self.processed_responses > 0 else 0),
            'response_history_size': len(self.response_history)
        }
    
    def get_recent_responses(self, count: int = 10) -> List[Dict[str, Any]]:
        """Get recent response processing results"""
        return self.response_history[-count:] if self.response_history else []
    
    def clear_history(self):
        """Clear response history"""
        self.response_history = []
        self.logger.info("Response processing history cleared")