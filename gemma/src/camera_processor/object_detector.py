"""Object detection using YOLOv6"""

import logging
import numpy as np
import cv2
from typing import List, Dict, Any, Optional, Tuple
import time

try:
    from ultralytics import YOLO
    YOLO_AVAILABLE = True
except ImportError:
    YOLO_AVAILABLE = False
    logging.warning("Ultralytics YOLO not available, using mock detector")

class DetectedObject:
    """Represents a detected object"""
    def __init__(self, class_id: int, class_name: str, confidence: float, 
                 bbox: Tuple[int, int, int, int], timestamp: float = None):
        self.class_id = class_id
        self.class_name = class_name
        self.confidence = confidence
        self.bbox = bbox  # (x1, y1, x2, y2)
        self.timestamp = timestamp or time.time()
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary"""
        return {
            'class_id': self.class_id,
            'class_name': self.class_name,
            'confidence': self.confidence,
            'bbox': self.bbox,
            'timestamp': self.timestamp
        }
    
    def __eq__(self, other):
        """Check equality based on class and position"""
        if not isinstance(other, DetectedObject):
            return False
        return (self.class_id == other.class_id and 
                self._bbox_overlap(other.bbox) > 0.5)
    
    def _bbox_overlap(self, other_bbox: Tuple[int, int, int, int]) -> float:
        """Calculate IoU overlap with another bounding box"""
        x1, y1, x2, y2 = self.bbox
        ox1, oy1, ox2, oy2 = other_bbox
        
        # Calculate intersection
        ix1 = max(x1, ox1)
        iy1 = max(y1, oy1)
        ix2 = min(x2, ox2)
        iy2 = min(y2, oy2)
        
        if ix2 <= ix1 or iy2 <= iy1:
            return 0.0
        
        intersection = (ix2 - ix1) * (iy2 - iy1)
        area1 = (x2 - x1) * (y2 - y1)
        area2 = (ox2 - ox1) * (oy2 - oy1)
        union = area1 + area2 - intersection
        
        return intersection / union if union > 0 else 0.0

class ObjectDetector:
    """YOLOv6 object detector with focus on humans and animals"""
    
    def __init__(self, model_path: str = "yolov6n.pt", confidence_threshold: float = 0.5):
        self.model_path = model_path
        self.confidence_threshold = confidence_threshold
        self.logger = logging.getLogger(__name__)
        
        # Target classes (COCO dataset class IDs)
        self.target_classes = {
            0: 'person',
            14: 'bird',
            15: 'cat',
            16: 'dog',
            17: 'horse',
            18: 'sheep',
            19: 'cow',
            20: 'elephant',
            21: 'bear',
            22: 'zebra',
            23: 'giraffe'
        }
        
        # Initialize model
        self.model = None
        self._load_model()
        
        # Object tracking
        self.previous_objects: List[DetectedObject] = []
        self.object_history: List[List[DetectedObject]] = []
        self.max_history = 10
    
    def _load_model(self):
        """Load YOLO model"""
        try:
            if YOLO_AVAILABLE:
                self.model = YOLO(self.model_path)
                self.logger.info(f"Loaded YOLO model: {self.model_path}")
            else:
                self.logger.warning("YOLO not available, using mock detector")
                self.model = None
        except Exception as e:
            self.logger.error(f"Error loading YOLO model: {e}")
            self.model = None
    
    def detect_objects(self, frame: np.ndarray) -> List[DetectedObject]:
        """Detect objects in frame"""
        if self.model is None:
            return self._mock_detect(frame)
        
        try:
            # Run inference
            results = self.model(frame, verbose=False)
            
            detected_objects = []
            for result in results:
                boxes = result.boxes
                if boxes is not None:
                    for box in boxes:
                        # Extract box data
                        xyxy = box.xyxy[0].cpu().numpy()
                        conf = box.conf[0].cpu().numpy()
                        cls = int(box.cls[0].cpu().numpy())
                        
                        # Check if it's a target class and meets confidence threshold
                        if cls in self.target_classes and conf >= self.confidence_threshold:
                            detected_objects.append(DetectedObject(
                                class_id=cls,
                                class_name=self.target_classes[cls],
                                confidence=float(conf),
                                bbox=(int(xyxy[0]), int(xyxy[1]), int(xyxy[2]), int(xyxy[3]))
                            ))
            
            return detected_objects
            
        except Exception as e:
            self.logger.error(f"Error during object detection: {e}")
            return []
    
    def _mock_detect(self, frame: np.ndarray) -> List[DetectedObject]:
        """Mock detection for testing when YOLO is not available"""
        # Simple mock: occasionally detect a "person" in the center
        if np.random.random() < 0.1:  # 10% chance
            h, w = frame.shape[:2]
            return [DetectedObject(
                class_id=0,
                class_name='person',
                confidence=0.8,
                bbox=(w//4, h//4, 3*w//4, 3*h//4)
            )]
        return []
    
    def get_object_changes(self, current_objects: List[DetectedObject]) -> Dict[str, List[DetectedObject]]:
        """Get object changes compared to previous frame"""
        changes = {
            'appeared': [],
            'disappeared': [],
            'current': current_objects
        }
        
        # Find appeared objects
        for obj in current_objects:
            if obj not in self.previous_objects:
                changes['appeared'].append(obj)
        
        # Find disappeared objects
        for obj in self.previous_objects:
            if obj not in current_objects:
                changes['disappeared'].append(obj)
        
        # Update object history
        self.object_history.append(current_objects.copy())
        if len(self.object_history) > self.max_history:
            self.object_history.pop(0)
        
        # Update previous objects
        self.previous_objects = current_objects.copy()
        
        return changes
    
    def annotate_frame(self, frame: np.ndarray, objects: List[DetectedObject]) -> np.ndarray:
        """Annotate frame with detected objects"""
        annotated_frame = frame.copy()
        
        for obj in objects:
            x1, y1, x2, y2 = obj.bbox
            
            # Draw bounding box
            cv2.rectangle(annotated_frame, (x1, y1), (x2, y2), (0, 255, 0), 2)
            
            # Draw label
            label = f"{obj.class_name}: {obj.confidence:.2f}"
            label_size = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, 0.5, 2)[0]
            cv2.rectangle(annotated_frame, (x1, y1 - label_size[1] - 10), 
                         (x1 + label_size[0], y1), (0, 255, 0), -1)
            cv2.putText(annotated_frame, label, (x1, y1 - 5), 
                       cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 0, 0), 2)
        
        return annotated_frame
    
    def get_detection_summary(self) -> Dict[str, Any]:
        """Get summary of recent detections"""
        if not self.object_history:
            return {'total_objects': 0, 'classes': {}}
        
        # Count objects by class across recent history
        class_counts = {}
        total_objects = 0
        
        for frame_objects in self.object_history:
            for obj in frame_objects:
                class_counts[obj.class_name] = class_counts.get(obj.class_name, 0) + 1
                total_objects += 1
        
        return {
            'total_objects': total_objects,
            'classes': class_counts,
            'frames_processed': len(self.object_history)
        }