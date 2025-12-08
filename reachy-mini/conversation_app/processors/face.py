#!/usr/bin/env python3
"""
Face Recognition Processor using face_recognition library.
"""

import os
import logging
import time
import shutil
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
    
    def __init__(self, known_faces_dir: str = './conversation_app/data/faces', event_callback=None):
        """
        Args:
            known_faces_dir: Directory containing subdirectories of known faces.
                            Structure: known_faces_dir/person_name/image1.jpg, image2.jpg, ...
            event_callback: Optional callback function for emitting events (event_type, data)
        """
        self.known_faces_dir = known_faces_dir
        self.known_face_encodings = []
        self.known_face_names = []
        self.event_callback = event_callback
        self.recently_seen_faces = {}  # name -> last_seen_timestamp
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
            
            # Cleanup old unknown faces on startup
            self.cleanup_old_unknown_faces()
            
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
    
    def cleanup_old_unknown_faces(self, max_age_minutes: int = 15) -> None:
        """
        Delete John Doe directories if they are older than max_age_minutes.
        
        Args:
            max_age_minutes: Maximum age in minutes before deletion (default: 15)
        """
        try:
            faces_path = Path(self.known_faces_dir)
            if not faces_path.exists():
                return
            
            # FIXED: Use time.time() to get a float timestamp compatible with st_mtime
            current_time = time.time()
            max_age_seconds = max_age_minutes * 60
            deleted_count = 0
            
            for person_dir in faces_path.iterdir():
                if not person_dir.is_dir():
                    continue
                
                # Check if it's a JohnDoe directory
                if person_dir.name.startswith("JohnDoe"):
                    # Get directory modification time (float timestamp)
                    dir_mtime = person_dir.stat().st_mtime
                    age_seconds = current_time - dir_mtime
                    
                    if age_seconds > max_age_seconds:
                        logger.info(f"Deleting old unknown face: {person_dir.name} (age: {age_seconds/60:.1f} minutes)")
                        shutil.rmtree(person_dir)
                        deleted_count += 1
            
            if deleted_count > 0:
                logger.info(f"Deleted {deleted_count} old unknown face directories")
                
        except Exception as e:
            logger.error(f"Error during cleanup of old unknown faces: {e}", exc_info=True)
            
    def _get_next_johndoe_id(self) -> int:
        """
        Find the next available ID for JohnDoe.
        """
        max_id = 0
        faces_path = Path(self.known_faces_dir)
        
        if not faces_path.exists():
            return 1
            
        for person_dir in faces_path.iterdir():
            if person_dir.is_dir() and person_dir.name.startswith("JohnDoe"):
                try:
                    # Extract number part
                    num_part = person_dir.name[7:] # "JohnDoe" is 7 chars
                    if num_part.isdigit():
                        current_id = int(num_part)
                        if current_id > max_id:
                            max_id = current_id
                except ValueError:
                    continue
                    
        return max_id + 1

    def _save_unknown_face(self, image: np.ndarray, location: Tuple[int, int, int, int]) -> Tuple[str, str]:
        """
        Save an unknown face to a new JohnDoe directory.
        
        Args:
            image: Full image in BGR format (OpenCV standard)
            location: Face location (top, right, bottom, left)
            
        Returns:
            Tuple of (name, image_path) - Name assigned and path to saved image
        """
        try:
            # Generate new name
            next_id = self._get_next_johndoe_id()
            name = f"JohnDoe{next_id}"
            
            # Create directory
            person_dir = Path(self.known_faces_dir) / name
            person_dir.mkdir(parents=True, exist_ok=True)
            
            # Crop face
            top, right, bottom, left = location
            
            # Add some padding if possible
            h, w, _ = image.shape
            pad_h = int((bottom - top) * 0.2)
            pad_w = int((right - left) * 0.2)
            
            y1 = max(0, top - pad_h)
            y2 = min(h, bottom + pad_h)
            x1 = max(0, left - pad_w)
            x2 = min(w, right + pad_w)
            
            face_image = image[y1:y2, x1:x2]
            
            # Save image (image is already in BGR format from process())
            import cv2
            image_path = person_dir / f"{name}_1.jpg"
            cv2.imwrite(str(image_path), face_image)
            logger.info(f"Saved new unknown face to: {image_path}")
            
            return name, str(image_path)
            
        except Exception as e:
            logger.error(f"Failed to save unknown face: {e}")
            return "Unknown", ""

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
                    ...
                ],
                'count': 2
            }
        """
        try:            
            # Convert BGR to RGB (face_recognition uses RGB)
            rgb_image = np.ascontiguousarray(image[:, :, ::-1])
            
            # Find all face locations and encodings in the current frame
            face_locations = face_recognition.face_locations(rgb_image)
            
            if not face_locations:
                return {
                    'processor': self.name,
                    'faces': [],
                    'count': 0
                }

            face_encodings = face_recognition.face_encodings(rgb_image, face_locations)
            
            faces = []
            reload_needed = False
            
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
                
                # If still unknown, save it!
                if name == "Unknown":
                    # Only save if the face is reasonably large/clear to avoid saving artifacts
                    # Face height
                    face_h = bottom - top
                    if face_h > 50: # Minimum pixel size
                        logger.info(f"Found unknown face (size {face_h}px), saving...")
                        # Pass original BGR image to save correctly
                        name, image_path = self._save_unknown_face(image, (top, right, bottom, left))
                        confidence = 0.0 # It's a perfect match to itself
                        reload_needed = True
                        
                        # Emit event for new face saved
                        if self.event_callback and name != "Unknown":
                            event_data = {
                                'name': name,
                                'location': [int(top), int(right), int(bottom), int(left)],
                                'image_path': image_path,
                                'timestamp': int(time.time() * 1000)
                            }
                            try:
                                self.event_callback('new_face_saved', event_data)
                                logger.info(f"Emitted new_face_saved event for {name}")
                            except Exception as e:
                                logger.error(f"Error emitting new_face_saved event: {e}")
                
                faces.append({
                    'name': name,
                    'confidence': confidence,
                    'location': [int(top), int(right), int(bottom), int(left)]
                })
            
            # If we saved a new face, we should reload our known faces
            if reload_needed:
                self.initialize()
            
            # Update recently seen faces and prune old entries
            current_time = time.time()
            for face in faces:
                if face['name'] != "Unknown":
                    self.recently_seen_faces[face['name']] = current_time
            
            # Prune entries older than 15 minutes
            max_age_seconds = 15 * 60
            self.recently_seen_faces = {
                name: timestamp 
                for name, timestamp in self.recently_seen_faces.items()
                if current_time - timestamp <= max_age_seconds
            }
            
            # Add recently_seen list to results
            recently_seen = list(self.recently_seen_faces.keys())
            
            return {
                'processor': self.name,
                'faces': faces,
                'count': len(faces),
                'recently_seen': recently_seen
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
