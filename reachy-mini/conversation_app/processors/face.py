#!/usr/bin/env python3
"""
Face Recognition Processor using face_recognition library.
"""

import os
import logging
import face_recognition     
import numpy as np
from typing import Any, Dict, List, Tuple
from pathlib import Path
from .base import ImageProcessor

logger = logging.getLogger(__name__)


class FaceRecognitionProcessor(ImageProcessor):
    """
    Face recognition processor using the face_recognition library (dlib-based).
    
    Detects faces in images and matches them against known faces.
    """
    
    def __init__(self, known_faces_dir: str = './conversation_app/data/faces'):
        """
        Args:
            known_faces_dir: Directory containing subdirectories of known faces.
                            Structure: known_faces_dir/person_name/image1.jpg, image2.jpg, ...
        """
        self.known_faces_dir = known_faces_dir
        self.known_face_encodings = []
        self.known_face_names = []
        logger.info(f"FaceRecognitionProcessor created with faces_dir: {known_faces_dir}")
    
    @property
    def name(self) -> str:
        return "face_recognition"
    
    def initialize(self) -> bool:
        """
        Load known faces from the directory.
        """
        try:
            # Create directory if it doesn't exist
            os.makedirs(self.known_faces_dir, exist_ok=True)
            
            # Load all known faces
            logger.info(f"Loading known faces from: {self.known_faces_dir}")
            
            faces_path = Path(self.known_faces_dir)
            loaded_count = 0
            
            # Iterate through subdirectories (each subdirectory = one person)
            for person_dir in faces_path.iterdir():
                if not person_dir.is_dir():
                    continue
                
                person_name = person_dir.name
                logger.info(f"Loading faces for: {person_name}")
                
                # Load all images for this person
                for image_file in person_dir.glob('*'):
                    if image_file.suffix.lower() not in ['.jpg', '.jpeg', '.png']:
                        continue
                    
                    try:
                        # Load image
                        image = face_recognition.load_image_file(str(image_file))
                        
                        # Get face encodings
                        encodings = face_recognition.face_encodings(image)
                        
                        if encodings:
                            # Use first face found in the image
                            self.known_face_encodings.append(encodings[0])
                            self.known_face_names.append(person_name)
                            loaded_count += 1
                            logger.info(f"  Loaded: {image_file.name}")
                        else:
                            logger.warning(f"  No face found in: {image_file.name}")
                    
                    except Exception as e:
                        logger.error(f"  Error loading {image_file.name}: {e}")
            
            logger.info(f"Loaded {loaded_count} known face encodings for {len(set(self.known_face_names))} people")
            return True
            
        except ImportError:
            logger.error("face_recognition package not installed. Run: pip install face_recognition")
            return False
        except Exception as e:
            logger.error(f"Failed to initialize face recognition: {e}", exc_info=True)
            return False
    
    def process(self, image: np.ndarray) -> Dict[str, Any]:
        """
        Detect and recognize faces in the image.
        
        Args:
            image: Input image in BGR format (OpenCV standard).
        
        Returns:
            Dictionary with recognized faces:
            {
                'processor': 'face_recognition',
                'faces': [
                    {
                        'name': 'John Doe',
                        'confidence': 0.6,  # Distance metric (lower = better match)
                        'location': [top, right, bottom, left]
                    },
                    {
                        'name': 'Unknown',
                        'confidence': None,
                        'location': [top, right, bottom, left]
                    }
                ],
                'count': 2
            }
        """
        try:            
            # Convert BGR to RGB (face_recognition uses RGB)
            #rgb_image = image[:, :, ::-1]
            rgb_image = np.ascontiguousarray(image[:, :, ::-1])
            
            logger.info(f"Processing image shape: {rgb_image.shape}, dtype: {rgb_image.dtype}, min: {rgb_image.min()}, max: {rgb_image.max()}")

            # Find all face locations and encodings in the current frame
            face_locations = face_recognition.face_locations(rgb_image)
            logger.info(f"Found {len(face_locations)} faces in image")

            face_encodings = face_recognition.face_encodings(rgb_image, face_locations)
            
            faces = []
            
            for (top, right, bottom, left), face_encoding in zip(face_locations, face_encodings):
                # Default to unknown
                name = "Unknown"
                confidence = None
                
                if self.known_face_encodings:
                    # Compare with known faces
                    distances = face_recognition.face_distance(self.known_face_encodings, face_encoding)
                    
                    # Find best match
                    best_match_index = np.argmin(distances)
                    best_distance = distances[best_match_index]
                    
                    # Use threshold of 0.6 (lower is better)
                    if best_distance < 0.6:
                        name = self.known_face_names[best_match_index]
                        confidence = float(best_distance)
                
                faces.append({
                    'name': name,
                    'confidence': confidence,
                    'location': [int(top), int(right), int(bottom), int(left)]
                })
            
            return {
                'processor': self.name,
                'faces': faces,
                'count': len(faces)
            }
            
        except Exception as e:
            logger.error(f"Error during face recognition: {e}", exc_info=True)
            return {
                'processor': self.name,
                'error': str(e),
                'faces': [],
                'count': 0
            }
    
    def cleanup(self):
        """
        Clear loaded face encodings.
        """
        self.known_face_encodings.clear()
        self.known_face_names.clear()
        logger.info("Face encodings cleared")
