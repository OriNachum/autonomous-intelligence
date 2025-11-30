#!/usr/bin/env python3
"""
Base class for image processors.
"""

from abc import ABC, abstractmethod
import numpy as np
from typing import Any, Dict, List, Optional


class ImageProcessor(ABC):
    """
    Abstract base class for all image processors.
    
    Each processor must implement:
    - process(): Core processing logic
    - name: Unique identifier for the processor
    """
    
    @abstractmethod
    def process(self, image: np.ndarray) -> Dict[str, Any]:
        """
        Process a single image (numpy array in BGR format) and return extracted information.
        
        Args:
            image: Input image as numpy array (H x W x C) in BGR format.
        
        Returns:
            Dictionary containing extracted information. Structure depends on processor type.
            Should always include:
            - 'processor': name of the processor
            - 'timestamp': processing timestamp (if applicable)
            - processor-specific data
        """
        pass
    
    @property
    @abstractmethod
    def name(self) -> str:
        """
        Return the unique name of the processor.
        
        Examples: 'yolo_v8', 'face_recognition', 'pose_estimation'
        """
        pass
    
    def initialize(self) -> bool:
        """
        Optional initialization method for loading models, etc.
        
        Returns:
            True if initialization successful, False otherwise.
        """
        return True
    
    def cleanup(self):
        """
        Optional cleanup method for releasing resources.
        """
        pass
