"""TTS queue implementation with sentence-level processing"""

import asyncio
import logging
from typing import List, Optional, Dict, Any
from asyncio import Queue, Lock
from dataclasses import dataclass
import time

@dataclass
class TTSQueueItem:
    """Item in the TTS queue"""
    text: str
    priority: int = 0
    timestamp: float = 0
    metadata: Dict[str, Any] = None
    
    def __post_init__(self):
        if self.timestamp == 0:
            self.timestamp = time.time()
        if self.metadata is None:
            self.metadata = {}

class TTSQueue:
    """Thread-safe TTS queue with priority support"""
    
    def __init__(self, max_size: int = 10, max_tokens: int = 500):
        self.max_size = max_size
        self.max_tokens = max_tokens
        self.logger = logging.getLogger(__name__)
        
        # Queue and synchronization
        self.queue: Queue = Queue(maxsize=max_size)
        self.lock = Lock()
        
        # State tracking
        self.current_item: Optional[TTSQueueItem] = None
        self.is_processing = False
        self.total_tokens = 0
        self.queue_history: List[TTSQueueItem] = []
        
        # Reset flag
        self.reset_requested = False
    
    async def add_sentences(self, sentences: List[str], priority: int = 0, 
                           metadata: Optional[Dict[str, Any]] = None) -> bool:
        """Add sentences to the queue"""
        async with self.lock:
            # Check if adding would exceed token limit
            total_new_tokens = sum(len(sentence.split()) for sentence in sentences)
            if self.total_tokens + total_new_tokens > self.max_tokens:
                self.logger.warning(f"Adding sentences would exceed token limit ({self.max_tokens})")
                return False
            
            # Add sentences as individual items
            added_count = 0
            for sentence in sentences:
                if self.queue.full():
                    self.logger.warning("TTS queue is full, dropping sentence")
                    break
                
                try:
                    item = TTSQueueItem(
                        text=sentence,
                        priority=priority,
                        metadata=metadata or {}
                    )
                    await self.queue.put(item)
                    self.total_tokens += len(sentence.split())
                    added_count += 1
                    
                except Exception as e:
                    self.logger.error(f"Error adding sentence to queue: {e}")
                    break
            
            self.logger.debug(f"Added {added_count} sentences to TTS queue")
            return added_count > 0
    
    async def get_next_item(self) -> Optional[TTSQueueItem]:
        """Get the next item from the queue"""
        try:
            # Check for reset request
            if self.reset_requested:
                return None
            
            item = await asyncio.wait_for(self.queue.get(), timeout=1.0)
            
            async with self.lock:
                self.current_item = item
                self.is_processing = True
                self.total_tokens -= len(item.text.split())
            
            return item
            
        except asyncio.TimeoutError:
            return None
        except Exception as e:
            self.logger.error(f"Error getting next item: {e}")
            return None
    
    async def mark_item_complete(self, item: TTSQueueItem):
        """Mark an item as complete"""
        async with self.lock:
            if self.current_item == item:
                self.queue_history.append(item)
                self.current_item = None
                self.is_processing = False
                
                # Keep history size reasonable
                if len(self.queue_history) > 50:
                    self.queue_history = self.queue_history[-25:]
    
    async def reset_queue(self):
        """Reset the queue and stop current processing"""
        async with self.lock:
            self.reset_requested = True
            
            # Clear the queue
            while not self.queue.empty():
                try:
                    await self.queue.get()
                    self.queue.task_done()
                except:
                    break
            
            # Reset counters
            self.total_tokens = 0
            self.current_item = None
            self.is_processing = False
            
            self.logger.info("TTS queue reset")
    
    async def acknowledge_reset(self):
        """Acknowledge that reset has been processed"""
        async with self.lock:
            self.reset_requested = False
    
    def is_empty(self) -> bool:
        """Check if queue is empty"""
        return self.queue.empty()
    
    def get_size(self) -> int:
        """Get current queue size"""
        return self.queue.qsize()
    
    def get_token_count(self) -> int:
        """Get current token count"""
        return self.total_tokens
    
    def is_reset_requested(self) -> bool:
        """Check if reset was requested"""
        return self.reset_requested
    
    def get_status(self) -> Dict[str, Any]:
        """Get queue status"""
        return {
            'size': self.get_size(),
            'token_count': self.get_token_count(),
            'is_processing': self.is_processing,
            'reset_requested': self.reset_requested,
            'current_item': self.current_item.text if self.current_item else None,
            'max_size': self.max_size,
            'max_tokens': self.max_tokens
        }