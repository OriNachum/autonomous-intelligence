"""
Image processing pipeline infrastructure.
"""

from .base import ImageProcessor
from .manager import ProcessorManager
from .yolo import YoloProcessor
from .face import FaceRecognitionProcessor

__all__ = ['ImageProcessor', 'ProcessorManager', 'YoloProcessor', 'FaceRecognitionProcessor']

