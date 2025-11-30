#!/usr/bin/env python3
"""
Gateway Video - Video processing component for Reachy Gateway
Refactored to use ReachySDK's internal MediaManager.
"""

import os
import time
import logging
import asyncio
from pathlib import Path
from collections import deque
from typing import Optional, Callable
import numpy as np

from .logger import get_logger
logger = logging.getLogger(__name__)

try:
    import cv2
    HAS_CV2 = True
except ImportError:
    HAS_CV2 = False

# Import processor infrastructure
try:
    from .processors import ProcessorManager, YoloProcessor, FaceRecognitionProcessor
    HAS_PROCESSORS = True
except ImportError:
    HAS_PROCESSORS = False
    logger.warning("Processors not available - image processing will be disabled")

class GatewayVideo:
    """
    Video processing component that wraps the ReachySDK Media Manager.
    Polls frames from the SDK, saves them, emits events, and runs image processors.
    """
    
    def __init__(self, media, event_callback: Callable, frame_interval: int = 10, enable_processors: bool = True):
        """
        Args:
            mini_sdk: The initialized ReachySDK instance.
            event_callback: Async callback for events.
            frame_interval: Processing interval in seconds (default: 0.1s = 10FPS).
                            Note: Changed from 'nth frame' to 'seconds' since we are polling.
            enable_processors: Enable image processors (YOLO, face recognition, etc.)
        """
        logger.info("Initializing Gateway Video (SDK Backend)")

        
        self.media = media
        self.emit_event = event_callback
        self.frame_interval = frame_interval
        # We now use time-based interval for polling, defaulting to ~10 FPS
        self.poll_interval = 0.1 
        
        self.videos_dir = os.getenv('VIDEOS_DIR', './videos')
        os.makedirs(self.videos_dir, exist_ok=True)
        
        self.max_videos = int(os.getenv('MAX_VIDEOS', '20'))
        self.video_files = deque(maxlen=self.max_videos)
        
        self.frame_count = 0
        self.saved_frame_count = 0
        self.shutdown_requested = False
        self.polling_task = None
        
        # Initialize image processors
        self.processor_manager = None
        if enable_processors and HAS_PROCESSORS:
            logger.info("Initializing image processors...")
            self.processor_manager = ProcessorManager(event_callback)
            
            # Register YOLO processor
            yolo = YoloProcessor(model_name='yolov8n.pt', confidence_threshold=0.5)
            self.processor_manager.register_processor(yolo)
            
            # Register Face Recognition processor
            face_rec = FaceRecognitionProcessor(known_faces_dir='./conversation_app/data/faces')
            self.processor_manager.register_processor(face_rec)
            
            logger.info("Image processors initialized")
        else:
            logger.info("Image processors disabled")
        
        if self.media is None:
            logger.warning("ReachySDK has no media backend initialized!")


    async def start(self):
        """Start the video polling loop."""
        if self.polling_task:
            return

        logger.info("Starting video polling loop...")
        self.shutdown_requested = False
        self.polling_task = asyncio.create_task(self._poll_loop())
        logger.info("Video polling started.")

    async def _poll_loop(self):
        """Continuously polls the SDK for the latest frame."""
        while not self.shutdown_requested:
            start_time = time.time()
            
            try:
                # 1. Get Frame from SDK (Returns BGR numpy array or None)
                # This is non-blocking in the SDK (it returns the last buffer)
                frame = self.media.get_frame()
                
                if frame is not None:
                    self.frame_count += 1
                    # Save frame asynchronously to avoid blocking the loop
                    asyncio.create_task(self._save_frame(frame.copy()))
                else:
                    # Optional: Log warning if stream is consistently empty
                    pass

            except Exception as e:
                logger.error(f"Error in video poll loop: {e}")
            
            # 2. Maintain consistent framerate
            elapsed = time.time() - start_time
            sleep_time = max(0.01, self.poll_interval - elapsed)
            await asyncio.sleep(sleep_time)

    async def _save_frame(self, frame_bgr: np.ndarray):
        """
        Save frame to disk and emit event.
        Args:
            frame_bgr: Frame data in BGR format (standard OpenCV/ReachySDK format)
        """
        try:
            timestamp = int(time.time() * 1000)
            filename = os.path.join(self.videos_dir, f"frame_{timestamp}.jpg")
            
            # Save to disk
            if HAS_CV2:
                # OpenCV handles BGR natively
                await asyncio.to_thread(cv2.imwrite, filename, frame_bgr)
            else:
                # Fallback to PIL (Requires RGB)
                from PIL import Image
                # Convert BGR -> RGB
                frame_rgb = frame_bgr[:, :, ::-1] 
                img = Image.fromarray(frame_rgb)
                await asyncio.to_thread(img.save, filename)
            
            self.saved_frame_count += 1
            
            # Rolling deletion logic
            if len(self.video_files) >= self.max_videos:
                oldest_file = self.video_files.popleft()
                if os.path.exists(oldest_file):
                    await asyncio.to_thread(os.remove, oldest_file)
            
            self.video_files.append(filename)
            
            # Emit event
            await self.emit_event("video_frame_captured", {
                "frame_number": self.saved_frame_count,
                "total_frames": self.frame_count,
                "file_path": filename,
                "timestamp": timestamp
            })
            
            # Process frame through image processors
            if self.processor_manager:
                await self.processor_manager.process_stream_frame(
                    frame_bgr, 
                    self.saved_frame_count, 
                    timestamp
                )
            
        except Exception as e:
            logger.error(f"Error saving frame: {e}", exc_info=True)

    def stop(self):
        """Stop polling."""
        logger.info("Stopping video polling...")
        self.shutdown_requested = True
        if self.polling_task:
            self.polling_task.cancel()
            self.polling_task = None

    def cleanup(self):
        self.stop()
        if self.processor_manager:
            self.processor_manager.cleanup()