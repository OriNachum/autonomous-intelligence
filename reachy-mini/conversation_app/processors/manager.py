#!/usr/bin/env python3
"""
Processor Manager - Orchestrates multiple image processors.
"""

import time
import logging
import asyncio
import numpy as np
from collections import deque
from typing import Any, Dict, List, Callable, Optional, Set
from .base import ImageProcessor
from ..logger import get_logger

logger = logging.getLogger(__name__)


class ResultFilter:
    """
    Filters vision detection results using a sliding window to ensure stability.
    
    Only emits events when the stable set of detections changes, preventing
    flickering from transient detections.
    """
    
    def __init__(self, window_duration: float = 1.0, threshold: float = 0.5):
        """
        Args:
            window_duration: Duration of sliding window in seconds (default: 1.0)
            threshold: Fraction of frames required for stable detection (default: 0.5)
        """
        self.window_duration = window_duration
        self.threshold = threshold
        self.result_window = deque()  # Store (timestamp, labels_set) tuples
        self.last_emitted_set: Optional[Set[str]] = None  # Last stable set that was emitted (None = not yet emitted)
        logger.info(f"ResultFilter initialized (window={window_duration}s, threshold={threshold})")
    
    def add_result(self, result: Dict[str, Any], timestamp: int) -> Optional[Set[str]]:
        """
        Add a new detection result to the sliding window.
        
        Args:
            result: Detection result from processor (must contain detections)
            timestamp: Timestamp in milliseconds
        
        Returns:
            Set of stable labels if state changed (should emit event), None otherwise
        """
        # Extract labels from result
        labels_set = self._extract_labels(result)
        
        # Add to window
        self.result_window.append((timestamp, labels_set))
        
        # Remove old entries outside the window
        window_start = timestamp - (self.window_duration * 1000)  # Convert to ms
        while self.result_window and self.result_window[0][0] < window_start:
            self.result_window.popleft()
        
        # Calculate stable set (labels that appear in >threshold% of frames)
        stable_set = self._calculate_stable_set()
        
        # Check if stable set changed
        if stable_set != self.last_emitted_set:
            self.last_emitted_set = stable_set.copy()
            return stable_set
        
        return None  # No change, don't emit
    
    def _extract_labels(self, result: Dict[str, Any]) -> Set[str]:
        """
        Extract labels from a detection result.
        
        Args:
            result: Detection result from processor
        
        Returns:
            Set of detected labels
        """
        labels = set()
        
        # Handle YOLO results
        if 'detections' in result:
            for detection in result['detections']:
                if 'label' in detection:
                    labels.add(detection['label'])
        
        # Handle face recognition results
        if 'faces' in result:
            for face in result['faces']:
                if face.get('name') != 'Unknown':
                    labels.add(f"person:{face.get('name')}")
                else:
                    labels.add("person:unknown")
        
        return labels
    
    def _calculate_stable_set(self) -> Set[str]:
        """
        Calculate the stable set of labels based on threshold.
        
        Returns:
            Set of labels that appear in >threshold% of frames in window
        """
        if not self.result_window:
            return set()
        
        # Count label occurrences
        label_counts: Dict[str, int] = {}
        for _, labels_set in self.result_window:
            for label in labels_set:
                label_counts[label] = label_counts.get(label, 0) + 1
        
        # Apply threshold
        window_size = len(self.result_window)
        threshold_count = window_size * self.threshold
        
        stable_labels = {
            label for label, count in label_counts.items()
            if count > threshold_count
        }
        
        return stable_labels


class ProcessorManager:
    """
    Manages multiple image processors and routes inputs to them.
    
    Responsibilities:
    - Register/Load processors
    - Route inputs (frames, files) to active processors
    - Aggregate results
    - Emit events via callback
    """
    
    def __init__(self, event_callback: Callable, enable_filtering: bool = True, min_emission_interval: float = 1.0):
        """
        Args:
            event_callback: Async callback for emitting events.
            enable_filtering: Enable result filtering (default: True)
            min_emission_interval: Minimum time in seconds between emissions per processor (default: 1.0)
        """
        self.processors: List[ImageProcessor] = []
        self.emit_event = event_callback
        self.enable_filtering = enable_filtering
        self.min_emission_interval = min_emission_interval
        
        # Initialize result filters per processor
        self.filters: Dict[str, ResultFilter] = {}
        
        # Track last emission time per processor (in seconds since epoch)
        self.last_emission_time: Dict[str, float] = {}
        
        logger.info(f"ProcessorManager initialized (filtering={'enabled' if enable_filtering else 'disabled'}, min_interval={min_emission_interval}s)")
    
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
                
                # Create a filter for this processor if filtering is enabled
                if self.enable_filtering:
                    self.filters[processor.name] = ResultFilter()
                
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
            
            # Apply filtering if enabled
            should_emit = True
            if self.enable_filtering and processor.name in self.filters:
                result_filter = self.filters[processor.name]
                stable_labels = result_filter.add_result(result, timestamp)
                
                if stable_labels is None:
                    # No change in stable set, don't emit
                    should_emit = False
                    logger.debug(f"Processor {processor.name}: No stable change, skipping event")
                else:
                    # State changed, add stable labels to result
                    result['stable_labels'] = list(stable_labels)
                    logger.info(f"Processor {processor.name}: Stable state changed to {stable_labels}")
            
            # Apply time-based rate limiting
            if should_emit:
                current_time = time.time()
                last_emission = self.last_emission_time.get(processor.name, 0)
                time_since_last = current_time - last_emission
                
                if time_since_last < self.min_emission_interval:
                    # Too soon since last emission
                    should_emit = False
                    logger.debug(f"Processor {processor.name}: Rate limited (only {time_since_last:.2f}s since last emission, minimum {self.min_emission_interval}s)")
            
            # Emit processor-specific event only if all checks pass
            if should_emit:
                event_name = f"{processor.name}_result"
                await self.emit_event(event_name, result)
                
                # Update last emission time
                self.last_emission_time[processor.name] = time.time()
                
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
