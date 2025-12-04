#!/usr/bin/env python3
"""
YOLO Object Detection Processor using YOLOv8.
"""

import logging
import numpy as np
from typing import Any, Dict, List, Optional
from .base import ImageProcessor

logger = logging.getLogger(__name__)


class YoloProcessor(ImageProcessor):
    """
    YOLO-based object detection processor.
    
    Uses Ultralytics YOLOv8 for real-time object detection.
    """
    
    def __init__(self, model_name: str = 'yolov8n.pt', confidence_threshold: float = 0.5):
        """
        Args:
            model_name: Name of the YOLO model to load (default: yolov8n - nano, fastest).
                       Options: yolov8n.pt, yolov8s.pt, yolov8m.pt, yolov8l.pt, yolov8x.pt
            confidence_threshold: Minimum confidence for detections (default: 0.5).
        """
        self.model_name = model_name
        self.confidence_threshold = confidence_threshold
        self.model = None
        logger.info(f"YoloProcessor created with model: {model_name}")
    
    @property
    def name(self) -> str:
        return "yolo_v8"
    
    def initialize(self) -> bool:
        """
        Load the YOLO model.
        """
        try:
            from ultralytics import YOLO
            import os
            from pathlib import Path
            
            model_path = self.model_name
            
            # Check if PROCESSOR_MODELS_DIR is set
            models_dir = os.environ.get("PROCESSOR_MODELS_DIR")
            if models_dir:
                potential_path = Path(models_dir) / self.model_name
                if potential_path.exists():
                    model_path = str(potential_path)
                    logger.info(f"Found model in models directory: {model_path}")
            
            logger.info(f"Loading YOLO model: {model_path}")
            self.model = YOLO(model_path)
            logger.info("YOLO model loaded successfully")
            return True
            
        except ImportError:
            logger.error("ultralytics package not installed. Run: pip install ultralytics")
            return False
        except Exception as e:
            logger.error(f"Failed to load YOLO model: {e}", exc_info=True)
            return False
    
    def process(self, image: np.ndarray) -> Dict[str, Any]:
        """
        Detect objects in the image.
        
        Args:
            image: Input image in BGR format.
        
        Returns:
            Dictionary with detected objects:
            {
                'processor': 'yolo_v8',
                'detections': [
                    {
                        'label': 'person',
                        'confidence': 0.95,
                        'bbox': [x1, y1, x2, y2]  # Top-left and bottom-right
                    },
                    ...
                ],
                'count': 3
            }
        """
        if self.model is None:
            return {
                'processor': self.name,
                'error': 'Model not initialized',
                'detections': [],
                'count': 0
            }
        
        try:
            # Run inference
            results = self.model(image, conf=self.confidence_threshold, verbose=False)
            
            # Extract detections
            detections = []
            for result in results:
                boxes = result.boxes
                for box in boxes:
                    # Extract box coordinates, confidence, and class
                    x1, y1, x2, y2 = box.xyxy[0].tolist()  # Bounding box coordinates
                    confidence = float(box.conf[0])
                    class_id = int(box.cls[0])
                    class_name = result.names[class_id]
                    
                    detections.append({
                        'label': class_name,
                        'confidence': confidence,
                        'bbox': [int(x1), int(y1), int(x2), int(y2)]
                    })
            
            return {
                'processor': self.name,
                'detections': detections,
                'count': len(detections)
            }
            
        except Exception as e:
            logger.error(f"Error during YOLO inference: {e}", exc_info=True)
            return {
                'processor': self.name,
                'error': str(e),
                'detections': [],
                'count': 0
            }
    
    def cleanup(self):
        """
        Release model resources.
        """
        self.model = None
        logger.info("YOLO model released")
