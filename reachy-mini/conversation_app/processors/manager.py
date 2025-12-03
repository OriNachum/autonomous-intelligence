#!/usr/bin/env python3
"""
Processor Manager - Orchestrates multiple image processors.
"""

import time
import logging
import asyncio
import numpy as np
from typing import Any, Dict, List, Callable, Optional
from .base import ImageProcessor
from ..logger import get_logger

logger = logging.getLogger(__name__)


class ProcessorManager:
    """
    Manages multiple image processors and routes inputs to them.
    
    Responsibilities:
    - Register/Load processors
    - Route inputs (frames, files) to active processors
    - Aggregate results
    - Emit events via callback
    """
    
    def __init__(self, event_callback: Callable):
        """
        Args:
            event_callback: Async callback for emitting events.
        """
        self.processors: List[ImageProcessor] = []
        self.emit_event = event_callback
        logger.info("ProcessorManager initialized")
    
    def register_processor(self, processor: ImageProcessor) -> bool:
        """
        Register a new processor.
        
        Args:
            processor: ImageProcessor instance to register.
        
        Returns:
            True if registration successful, False otherwise.
        """
        try:
            # Initialize the processor
            if processor.initialize():
                self.processors.append(processor)
                logger.info(f"Registered processor: {processor.name}")
                return True
            else:
                logger.error(f"Failed to initialize processor: {processor.name}")
                return False
        except Exception as e:
            logger.error(f"Error registering processor {processor.name}: {e}", exc_info=True)
            return False
    
    async def process_stream_frame(self, frame: np.ndarray, frame_number: int, timestamp: int):
        """
        Process a single frame from the video stream through all registered processors.
        
        Args:
            frame: Input image as numpy array (H x W x C) in BGR format.
            frame_number: Frame number in the stream.
            timestamp: Timestamp in milliseconds.
        """
        if not self.processors:
            return
        
        # Process frame through each processor asynchronously
        tasks = []
        for processor in self.processors:
            task = asyncio.create_task(
                self._process_with_processor(processor, frame, frame_number, timestamp)
            )
            tasks.append(task)
        
        # Wait for all processors to complete
        await asyncio.gather(*tasks, return_exceptions=True)
    
    async def _process_with_processor(
        self, 
        processor: ImageProcessor, 
        frame: np.ndarray, 
        frame_number: int,
        timestamp: int
    ):
        """
        Process frame with a single processor and emit event.
        
        Args:
            processor: Processor to use.
            frame: Input image.
            frame_number: Frame number.
            timestamp: Timestamp in milliseconds.
        """
        try:
            start_time = time.time()
            
            # Run processor in thread pool to avoid blocking
            result = await asyncio.to_thread(processor.process, frame)
            
            processing_time = (time.time() - start_time) * 1000  # ms
            
            # Add metadata to result
            result['frame_number'] = frame_number
            result['timestamp'] = timestamp
            result['processing_time_ms'] = processing_time
            
            # Emit processor-specific event
            event_name = f"{processor.name}_result"
            await self.emit_event(event_name, result)
            
            # Audit Log
            get_logger().log_vision_event(processor.name, result)
            
            logger.debug(f"Processor {processor.name} completed in {processing_time:.2f}ms")
            
        except Exception as e:
            logger.error(f"Error processing frame with {processor.name}: {e}", exc_info=True)
    
    async def process_single_image(self, image_path: str) -> Dict[str, Any]:
        """
        Process a single image file through all registered processors.
        
        Args:
            image_path: Path to the image file.
        
        Returns:
            Dictionary mapping processor names to their results.
        """
        import cv2
        
        # Load image
        image = await asyncio.to_thread(cv2.imread, image_path)
        if image is None:
            logger.error(f"Failed to load image: {image_path}")
            return {}
        
        results = {}
        timestamp = int(time.time() * 1000)
        
        for processor in self.processors:
            try:
                result = await asyncio.to_thread(processor.process, image)
                result['timestamp'] = timestamp
                result['source'] = image_path
                results[processor.name] = result
            except Exception as e:
                logger.error(f"Error processing image with {processor.name}: {e}", exc_info=True)
                results[processor.name] = {'error': str(e)}
        
        return results
    
    async def process_batch_images(self, image_paths: List[str]) -> List[Dict[str, Any]]:
        """
        Process a batch of images through all registered processors.
        
        Args:
            image_paths: List of image file paths.
        
        Returns:
            List of result dictionaries (one per image).
        """
        tasks = [self.process_single_image(path) for path in image_paths]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        return results
    
    def cleanup(self):
        """
        Cleanup all processors.
        """
        logger.info("Cleaning up ProcessorManager")
        for processor in self.processors:
            try:
                processor.cleanup()
            except Exception as e:
                logger.error(f"Error cleaning up processor {processor.name}: {e}")
        self.processors.clear()
