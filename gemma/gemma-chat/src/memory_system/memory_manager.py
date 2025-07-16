"""Memory manager that coordinates fact distillation and immediate memory"""

import asyncio
import logging
import time
from typing import Dict, Any, List, Optional

from .fact_distiller import FactDistiller, Fact
from .immediate_memory import ImmediateMemory
from .long_term_memory import LongTermMemory
from ..event_system import EventConsumer, EventProducer, EventType, GemmaEvent
from ..config import Config

class MemoryManager:
    """Manages the complete memory system including distillation and storage"""
    
    def __init__(self, config: Config):
        self.config = config
        self.logger = logging.getLogger(__name__)
        
        # Memory components
        self.fact_distiller = FactDistiller(
            model_name=config.MODEL_NAME if hasattr(config, 'MODEL_NAME') else "microsoft/DialoGPT-medium",
            cache_dir=config.MODEL_CACHE_DIR if hasattr(config, 'MODEL_CACHE_DIR') else "./models"
        )
        self.immediate_memory = ImmediateMemory(
            max_facts=config.IMMEDIATE_MEMORY_SIZE,
            relevance_threshold=0.3
        )
        self.long_term_memory = LongTermMemory(
            milvus_host=config.MILVUS_HOST,
            milvus_port=config.MILVUS_PORT,
            neo4j_uri=config.NEO4J_URI,
            neo4j_user=config.NEO4J_USER,
            neo4j_password=config.NEO4J_PASSWORD
        )
        
        # Event system
        self.event_consumer = EventConsumer(config, "memory_manager")
        self.event_producer = EventProducer(config, "memory_manager")
        
        # Processing state
        self.running = False
        self.processing_active = False
        
        # Memory processing queue
        self.processing_queue = asyncio.Queue()
        
        # Conversation tracking
        self.conversation_buffer = []
        self.max_buffer_size = 10
        self.last_user_input = None
        self.last_assistant_response = None
        self.last_context = None
        
        # Statistics
        self.conversations_processed = 0
        self.facts_injected = 0
        self.processing_times = []
        
        # Register event handlers
        self._register_event_handlers()
    
    def _register_event_handlers(self):
        """Register event handlers for memory processing"""
        # We'll listen for conversation events and distill facts from them
        # For now, we'll use a custom event type for memory processing
        pass
    
    async def start(self):
        """Start the memory manager"""
        self.logger.info("Starting memory manager")
        
        # Connect to event system
        await self.event_consumer.connect()
        await self.event_producer.connect()
        
        # Start consuming events
        await self.event_consumer.start_consuming()
        
        self.running = True
        self.processing_active = True
        
        # Start processing loop
        asyncio.create_task(self._processing_loop())
        
        self.logger.info("Memory manager started")
    
    async def stop(self):
        """Stop the memory manager"""
        self.logger.info("Stopping memory manager")
        
        self.running = False
        self.processing_active = False
        
        # Stop event system
        await self.event_consumer.stop_consuming()
        await self.event_producer.disconnect()
        await self.long_term_memory.close()
        
        self.logger.info("Memory manager stopped")
    
    async def _processing_loop(self):
        """Main memory processing loop"""
        while self.processing_active:
            try:
                # Process queued memory tasks
                try:
                    task = await asyncio.wait_for(self.processing_queue.get(), timeout=1.0)
                    await self._process_memory_task(task)
                except asyncio.TimeoutError:
                    continue
                    
            except Exception as e:
                self.logger.error(f"Error in memory processing loop: {e}")
                await asyncio.sleep(0.1)
    
    async def _process_memory_task(self, task: Dict[str, Any]):
        """Process a memory task"""
        task_type = task.get('type')
        
        if task_type == 'conversation':
            await self._process_conversation(
                task['user_input'],
                task['assistant_response'],
                task.get('context')
            )
        elif task_type == 'inject_facts':
            await self._inject_facts_into_context(
                task['query'],
                task.get('context'),
                task.get('callback')
            )
    
    async def process_conversation(self, 
                                 user_input: str,
                                 assistant_response: str,
                                 context: Optional[Dict[str, Any]] = None):
        """Process a conversation for fact distillation"""
        task = {
            'type': 'conversation',
            'user_input': user_input,
            'assistant_response': assistant_response,
            'context': context,
            'timestamp': time.time()
        }
        await self.processing_queue.put(task)
    
    async def _process_conversation(self,
                                  user_input: str,
                                  assistant_response: str,
                                  context: Optional[Dict[str, Any]] = None):
        """Process conversation and distill facts"""
        start_time = time.time()
        
        try:
            # Store conversation parts for tracking
            self.last_user_input = user_input
            self.last_assistant_response = assistant_response
            self.last_context = context
            
            # Add to conversation buffer
            conversation_entry = {
                'user_input': user_input,
                'assistant_response': assistant_response,
                'context': context,
                'timestamp': time.time()
            }
            self.conversation_buffer.append(conversation_entry)
            
            # Trim buffer
            if len(self.conversation_buffer) > self.max_buffer_size:
                self.conversation_buffer.pop(0)
            
            # Distill facts from the conversation
            facts = await self.fact_distiller.distill_facts_from_conversation(
                user_input, assistant_response, context
            )
            
            # Add facts to immediate memory
            if facts:
                added_count = await self.immediate_memory.add_facts(facts)
                self.logger.debug(f"Added {added_count} facts to immediate memory")
                
                # Archive important facts to long-term memory
                important_facts = [f for f in facts if f.importance > 0.7]
                if important_facts:
                    archived_count = await self.long_term_memory.archive_facts(important_facts)
                    self.logger.debug(f"Archived {archived_count} important facts to long-term memory")
            
            # Update statistics
            processing_time = time.time() - start_time
            self.conversations_processed += 1
            self.processing_times.append(processing_time)
            
            if len(self.processing_times) > 100:
                self.processing_times.pop(0)
            
            self.logger.debug(f"Processed conversation in {processing_time:.2f}s, distilled {len(facts)} facts")
            
        except Exception as e:
            self.logger.error(f"Error processing conversation: {e}")
    
    async def inject_relevant_facts(self,
                                  query: str,
                                  context: Optional[Dict[str, Any]] = None,
                                  max_facts: int = 5) -> List[Fact]:
        """Inject relevant facts into current context"""
        try:
            # Retrieve relevant facts
            relevant_facts = await self.immediate_memory.retrieve_relevant_facts(
                query, context, max_facts
            )
            
            self.facts_injected += len(relevant_facts)
            
            if relevant_facts:
                self.logger.debug(f"Injected {len(relevant_facts)} relevant facts for query: {query[:30]}...")
            
            return relevant_facts
            
        except Exception as e:
            self.logger.error(f"Error injecting facts: {e}")
            return []
    
    async def get_memory_context(self, 
                               query: str,
                               context: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Get memory context for model inference"""
        try:
            # Get relevant facts from immediate memory
            relevant_facts = await self.inject_relevant_facts(query, context)
            
            # Search long-term memory for additional relevant facts
            long_term_facts = await self.long_term_memory.search_facts(query, max_results=5)
            
            # Get recent facts
            recent_facts = self.immediate_memory.get_recent_facts(hours=1.0)
            
            # Get important facts
            important_facts = self.immediate_memory.get_important_facts(min_importance=0.8)
            
            # Format facts for injection
            memory_context = {
                'relevant_facts': [fact.content for fact in relevant_facts],
                'long_term_facts': [fact.content for fact in long_term_facts],
                'recent_facts': [fact.content for fact in recent_facts[-5:]],  # Last 5 recent facts
                'important_facts': [fact.content for fact in important_facts[-3:]],  # Top 3 important facts
                'fact_count': len(self.immediate_memory.facts),
                'memory_utilization': len(self.immediate_memory.facts) / self.immediate_memory.max_facts
            }
            
            return memory_context
            
        except Exception as e:
            self.logger.error(f"Error getting memory context: {e}")
            return {}
    
    def format_facts_for_prompt(self, facts: List[Fact]) -> str:
        """Format facts for inclusion in model prompt"""
        if not facts:
            return ""
        
        fact_strings = []
        for fact in facts:
            # Include confidence and recency indicators
            age_hours = (time.time() - fact.timestamp) / 3600
            if age_hours < 1:
                recency = "recent"
            elif age_hours < 24:
                recency = "today"
            else:
                recency = "older"
            
            fact_string = f"- {fact.content} ({recency}, confidence: {fact.confidence:.1f})"
            fact_strings.append(fact_string)
        
        return "Relevant facts from memory:\n" + "\n".join(fact_strings) + "\n"
    
    async def clear_memory(self):
        """Clear all memory"""
        self.immediate_memory.clear_memory()
        self.conversation_buffer = []
        self.last_user_input = None
        self.last_assistant_response = None
        self.last_context = None
        # Note: Long-term memory is not cleared as it's meant to be persistent
        self.logger.info("Cleared immediate memory")
    
    async def export_memory(self) -> Dict[str, Any]:
        """Export complete memory state"""
        return {
            'immediate_memory': self.immediate_memory.export_facts(),
            'conversation_buffer': self.conversation_buffer,
            'statistics': self.get_statistics(),
            'export_timestamp': time.time()
        }
    
    async def import_memory(self, memory_data: Dict[str, Any]) -> bool:
        """Import memory state"""
        try:
            # Import immediate memory facts
            if 'immediate_memory' in memory_data:
                imported_count = self.immediate_memory.import_facts(memory_data['immediate_memory'])
                self.logger.info(f"Imported {imported_count} facts to immediate memory")
            
            # Import conversation buffer
            if 'conversation_buffer' in memory_data:
                self.conversation_buffer = memory_data['conversation_buffer'][-self.max_buffer_size:]
                self.logger.info(f"Imported {len(self.conversation_buffer)} conversation entries")
            
            return True
            
        except Exception as e:
            self.logger.error(f"Error importing memory: {e}")
            return False
    
    def get_statistics(self) -> Dict[str, Any]:
        """Get comprehensive memory statistics"""
        avg_processing_time = (sum(self.processing_times) / len(self.processing_times) 
                             if self.processing_times else 0)
        
        return {
            'running': self.running,
            'conversations_processed': self.conversations_processed,
            'facts_injected': self.facts_injected,
            'avg_processing_time': avg_processing_time,
            'conversation_buffer_size': len(self.conversation_buffer),
            'immediate_memory': self.immediate_memory.get_statistics(),
            'long_term_memory': self.long_term_memory.get_statistics(),
            'fact_distiller': self.fact_distiller.get_statistics(),
            'queue_size': self.processing_queue.qsize()
        }
    
    def get_memory_summary(self) -> Dict[str, Any]:
        """Get a summary of current memory state"""
        stats = self.immediate_memory.get_statistics()
        
        # Get sample facts from each category
        category_samples = {}
        for category, facts in self.immediate_memory.facts_by_category.items():
            if facts:
                # Get most recent fact from each category
                recent_fact = max(facts, key=lambda f: f.timestamp)
                category_samples[category] = recent_fact.content[:100] + "..." if len(recent_fact.content) > 100 else recent_fact.content
        
        return {
            'total_facts': stats['total_facts'],
            'memory_utilization': f"{stats['memory_utilization']:.1%}",
            'categories': list(stats['facts_by_category'].keys()),
            'category_samples': category_samples,
            'recent_conversations': len(self.conversation_buffer),
            'last_processed': self.last_user_input[:50] + "..." if self.last_user_input and len(self.last_user_input) > 50 else self.last_user_input
        }