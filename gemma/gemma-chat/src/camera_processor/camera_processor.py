"""Camera processing loop with GStreamer and object detection"""

import asyncio
import logging
import cv2
import numpy as np
from typing import Optional, Dict, Any, List
import time
import threading
from queue import Queue as ThreadQueue

from .object_detector import ObjectDetector, DetectedObject
from ..event_system import EventProducer, EventType, CameraEvent
from ..config import Config

class CameraProcessor:
    """Camera processing with GStreamer and object detection"""
    
    def __init__(self, config: Config):
        self.config = config
        self.logger = logging.getLogger(__name__)
        
        # Camera configuration
        self.camera_device = config.CAMERA_DEVICE
        self.camera_width = config.CAMERA_WIDTH
        self.camera_height = config.CAMERA_HEIGHT
        self.camera_fps = config.CAMERA_FPS
        
        # Object detection
        self.object_detector = ObjectDetector(
            model_path=config.YOLO_MODEL_PATH,
            confidence_threshold=config.DETECTION_CONFIDENCE
        )
        
        # Event system
        self.event_producer = EventProducer(config, "camera_processor")
        
        # Camera capture
        self.cap: Optional[cv2.VideoCapture] = None
        self.running = False
        
        # Frame processing
        self.frame_queue = ThreadQueue(maxsize=5)
        self.current_frame: Optional[np.ndarray] = None
        self.frame_count = 0
        self.last_frame_time = 0
        
        # Performance tracking
        self.fps_counter = 0
        self.fps_start_time = time.time()
        self.processing_times = []
        
        # Threading
        self.capture_thread: Optional[threading.Thread] = None
        self.processing_active = False
    
    async def start(self):
        """Start camera processing"""
        self.logger.info("Starting camera processor")
        
        # Connect to event system
        await self.event_producer.connect()
        
        # Initialize camera
        if not self._initialize_camera():
            self.logger.error("Failed to initialize camera")
            return False
        
        self.running = True
        self.processing_active = True
        
        # Start capture thread
        self.capture_thread = threading.Thread(target=self._capture_loop, daemon=True)
        self.capture_thread.start()
        
        # Start processing loop
        asyncio.create_task(self._processing_loop())
        
        self.logger.info("Camera processor started")
        return True
    
    async def stop(self):
        """Stop camera processing"""
        self.logger.info("Stopping camera processor")
        
        self.running = False
        self.processing_active = False
        
        # Wait for capture thread
        if self.capture_thread and self.capture_thread.is_alive():
            self.capture_thread.join(timeout=2.0)
        
        # Release camera
        if self.cap:
            self.cap.release()
            self.cap = None
        
        # Disconnect from event system
        await self.event_producer.disconnect()
        
        self.logger.info("Camera processor stopped")
    
    def _initialize_camera(self) -> bool:
        """Initialize camera with GStreamer pipeline"""
        try:
            # Try GStreamer pipeline first
            gst_pipeline = (
                f"nvarguscamerasrc sensor-id=0 ! "
                f"video/x-raw(memory:NVMM), width={self.camera_width}, height={self.camera_height}, "
                f"format=NV12, framerate={self.camera_fps}/1 ! "
                f"nvvidconv ! video/x-raw, format=BGRx ! "
                f"videoconvert ! video/x-raw, format=BGR ! appsink"
            )
            
            self.cap = cv2.VideoCapture(gst_pipeline, cv2.CAP_GSTREAMER)
            
            if not self.cap.isOpened():
                self.logger.warning("GStreamer pipeline failed, trying standard camera")
                # Fallback to standard camera
                self.cap = cv2.VideoCapture(self.camera_device)
                
                if not self.cap.isOpened():
                    self.logger.error("Cannot open camera")
                    return False
                
                # Set camera properties
                self.cap.set(cv2.CAP_PROP_FRAME_WIDTH, self.camera_width)
                self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, self.camera_height)
                self.cap.set(cv2.CAP_PROP_FPS, self.camera_fps)
            
            # Test frame capture
            ret, frame = self.cap.read()
            if not ret:
                self.logger.error("Cannot read from camera")
                return False
            
            self.logger.info(f"Camera initialized: {frame.shape} at {self.camera_fps} FPS")
            return True
            
        except Exception as e:
            self.logger.error(f"Error initializing camera: {e}")
            return False
    
    def _capture_loop(self):
        """Camera capture loop running in separate thread"""
        while self.running:
            try:
                ret, frame = self.cap.read()
                if not ret:
                    self.logger.warning("Failed to read frame")
                    continue
                
                # Add frame to queue (drop oldest if full)
                if self.frame_queue.full():
                    try:
                        self.frame_queue.get_nowait()
                    except:
                        pass
                
                self.frame_queue.put(frame)
                self.frame_count += 1
                
                # Update FPS counter
                self.fps_counter += 1
                if time.time() - self.fps_start_time > 1.0:
                    actual_fps = self.fps_counter / (time.time() - self.fps_start_time)
                    self.logger.debug(f"Capture FPS: {actual_fps:.1f}")
                    self.fps_counter = 0
                    self.fps_start_time = time.time()
                
                # Control frame rate
                time.sleep(1.0 / self.camera_fps)
                
            except Exception as e:
                self.logger.error(f"Error in capture loop: {e}")
                time.sleep(0.1)
    
    async def _processing_loop(self):
        """Main processing loop"""
        while self.processing_active:
            try:
                # Get frame from queue
                frame = await self._get_frame()
                if frame is None:
                    await asyncio.sleep(0.01)
                    continue
                
                # Process frame
                await self._process_frame(frame)
                
            except Exception as e:
                self.logger.error(f"Error in processing loop: {e}")
                await asyncio.sleep(0.1)
    
    async def _get_frame(self) -> Optional[np.ndarray]:
        """Get frame from capture queue"""
        try:
            if not self.frame_queue.empty():
                return self.frame_queue.get_nowait()
        except:
            pass
        return None
    
    async def _process_frame(self, frame: np.ndarray):
        """Process a single frame"""
        start_time = time.time()
        
        try:
            # Update current frame
            self.current_frame = frame.copy()
            
            # Detect objects
            detected_objects = self.object_detector.detect_objects(frame)
            
            # Get object changes
            changes = self.object_detector.get_object_changes(detected_objects)
            
            # Send frame event
            await self._send_frame_event(frame, detected_objects)
            
            # Send object change events
            await self._send_object_events(changes)
            
            # Update performance metrics
            processing_time = time.time() - start_time
            self.processing_times.append(processing_time)
            if len(self.processing_times) > 100:
                self.processing_times.pop(0)
            
            self.last_frame_time = time.time()
            
        except Exception as e:
            self.logger.error(f"Error processing frame: {e}")
    
    async def _send_frame_event(self, frame: np.ndarray, objects: List[DetectedObject]):
        """Send camera frame event"""
        try:
            # Encode frame as JPEG for transmission
            _, buffer = cv2.imencode('.jpg', frame)
            frame_data = buffer.tobytes()
            
            # Create event
            event = CameraEvent(
                event_type=EventType.CAMERA_FRAME,
                frame_data=frame_data,
                detections=[obj.to_dict() for obj in objects]
            )
            
            await self.event_producer.send_event(event)
            
        except Exception as e:
            self.logger.error(f"Error sending frame event: {e}")
    
    async def _send_object_events(self, changes: Dict[str, List[DetectedObject]]):
        """Send object detection events"""
        try:
            # Send appeared objects
            for obj in changes['appeared']:
                event = CameraEvent(
                    event_type=EventType.OBJECT_DETECTED,
                    detections=[obj.to_dict()]
                )
                await self.event_producer.send_event(event)
            
            # Send disappeared objects
            for obj in changes['disappeared']:
                event = CameraEvent(
                    event_type=EventType.OBJECT_DISAPPEARED,
                    detections=[obj.to_dict()]
                )
                await self.event_producer.send_event(event)
                
        except Exception as e:
            self.logger.error(f"Error sending object events: {e}")
    
    def get_current_frame(self) -> Optional[np.ndarray]:
        """Get current frame"""
        return self.current_frame
    
    def get_annotated_frame(self) -> Optional[np.ndarray]:
        """Get current frame with object annotations"""
        if self.current_frame is None:
            return None
        
        # Get current objects
        objects = self.object_detector.previous_objects
        return self.object_detector.annotate_frame(self.current_frame, objects)
    
    def get_status(self) -> Dict[str, Any]:
        """Get camera processor status"""
        avg_processing_time = np.mean(self.processing_times) if self.processing_times else 0
        
        return {
            'running': self.running,
            'frame_count': self.frame_count,
            'last_frame_time': self.last_frame_time,
            'avg_processing_time': avg_processing_time,
            'camera_resolution': (self.camera_width, self.camera_height),
            'camera_fps': self.camera_fps,
            'detection_summary': self.object_detector.get_detection_summary()
        }