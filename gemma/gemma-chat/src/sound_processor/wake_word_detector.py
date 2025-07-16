"""Wake word detection for Gemma"""

import logging
import numpy as np
from typing import List, Optional, Tuple
import time
import re

try:
    import speech_recognition as sr
    SPEECH_RECOGNITION_AVAILABLE = True
except ImportError:
    SPEECH_RECOGNITION_AVAILABLE = False
    logging.warning("SpeechRecognition not available, using simple wake word detection")

class WakeWordDetector:
    """Wake word detection for 'Gemma' and 'Hey Gemma'"""
    
    def __init__(self, wake_words: List[str] = None, sample_rate: int = 16000):
        self.wake_words = wake_words or ["gemma", "hey gemma"]
        self.sample_rate = sample_rate
        self.logger = logging.getLogger(__name__)
        
        # Speech recognition
        self.recognizer = None
        self.microphone = None
        
        # Wake word patterns
        self.wake_word_patterns = [
            r'\b(hey\s+)?gemma\b',
            r'\bgemma\b',
            r'\bhey\s+gemma\b'
        ]
        
        # Detection state
        self.last_detection_time = 0
        self.detection_cooldown = 2.0  # seconds
        self.confidence_threshold = 0.7
        
        # Audio processing
        self.audio_buffer = []
        self.buffer_duration = 3.0  # seconds
        self.buffer_size = int(sample_rate * self.buffer_duration)
        
        # Statistics
        self.total_detections = 0
        self.false_positives = 0
        self.detection_history = []
        
        # Initialize speech recognition
        self._initialize_recognition()
    
    def _initialize_recognition(self):
        """Initialize speech recognition"""
        try:
            if SPEECH_RECOGNITION_AVAILABLE:
                self.recognizer = sr.Recognizer()
                self.logger.info("Speech recognition initialized")
            else:
                self.logger.warning("Speech recognition not available")
        except Exception as e:
            self.logger.error(f"Error initializing speech recognition: {e}")
    
    def process_audio(self, audio_data: np.ndarray) -> Tuple[bool, Optional[str], float]:
        """Process audio for wake word detection"""
        # Add to buffer
        self.audio_buffer.extend(audio_data.tolist())
        
        # Trim buffer
        if len(self.audio_buffer) > self.buffer_size:
            self.audio_buffer = self.audio_buffer[-self.buffer_size:]
        
        # Check cooldown
        current_time = time.time()
        if current_time - self.last_detection_time < self.detection_cooldown:
            return False, None, 0.0
        
        # Process audio for wake word
        if len(self.audio_buffer) < self.sample_rate:  # Need at least 1 second
            return False, None, 0.0
        
        # Get recent audio
        recent_audio = np.array(self.audio_buffer[-self.sample_rate:])
        
        # Detect wake word
        return self._detect_wake_word(recent_audio)
    
    def _detect_wake_word(self, audio_data: np.ndarray) -> Tuple[bool, Optional[str], float]:
        """Detect wake word in audio data"""
        if self.recognizer is None:
            return self._simple_wake_word_detection(audio_data)
        
        try:
            # Convert to audio format expected by speech_recognition
            audio_data_int16 = (audio_data * 32767).astype(np.int16)
            
            # Create AudioData object
            audio = sr.AudioData(
                audio_data_int16.tobytes(),
                self.sample_rate,
                2  # 2 bytes per sample for int16
            )
            
            # Recognize speech
            try:
                text = self.recognizer.recognize_google(audio, language='en-US')
                text = text.lower()
                
                # Check for wake words
                for pattern in self.wake_word_patterns:
                    if re.search(pattern, text):
                        self.logger.info(f"Wake word detected: '{text}'")
                        self.last_detection_time = time.time()
                        self.total_detections += 1
                        
                        # Add to history
                        self.detection_history.append({
                            'time': self.last_detection_time,
                            'text': text,
                            'confidence': 0.8  # Google API doesn't provide confidence
                        })
                        
                        return True, text, 0.8
                        
            except sr.UnknownValueError:
                # No speech recognized
                pass
            except sr.RequestError as e:
                self.logger.error(f"Speech recognition error: {e}")
                
        except Exception as e:
            self.logger.error(f"Error in wake word detection: {e}")
        
        return False, None, 0.0
    
    def _simple_wake_word_detection(self, audio_data: np.ndarray) -> Tuple[bool, Optional[str], float]:
        """Simple wake word detection based on audio patterns"""
        # This is a very basic implementation
        # In a real system, you'd use a proper wake word detection model
        
        # Calculate audio energy
        energy = np.sqrt(np.mean(audio_data ** 2))
        
        # Simple threshold-based detection
        if energy > 0.02:  # Adjust threshold as needed
            # Mock detection with low probability
            if np.random.random() < 0.05:  # 5% chance when energy is high
                self.logger.debug("Mock wake word detected")
                self.last_detection_time = time.time()
                self.total_detections += 1
                
                detected_word = np.random.choice(self.wake_words)
                confidence = 0.6 + np.random.random() * 0.3  # 0.6-0.9
                
                self.detection_history.append({
                    'time': self.last_detection_time,
                    'text': detected_word,
                    'confidence': confidence
                })
                
                return True, detected_word, confidence
        
        return False, None, 0.0
    
    def is_wake_word(self, text: str) -> bool:
        """Check if text contains a wake word"""
        text = text.lower()
        for pattern in self.wake_word_patterns:
            if re.search(pattern, text):
                return True
        return False
    
    def get_buffer_audio(self) -> np.ndarray:
        """Get current audio buffer"""
        return np.array(self.audio_buffer)
    
    def get_statistics(self) -> dict:
        """Get wake word detection statistics"""
        return {
            'total_detections': self.total_detections,
            'false_positives': self.false_positives,
            'detection_rate': len(self.detection_history),
            'last_detection_time': self.last_detection_time,
            'buffer_size': len(self.audio_buffer),
            'recent_detections': self.detection_history[-10:] if self.detection_history else [],
            'wake_words': self.wake_words
        }
    
    def reset(self):
        """Reset wake word detector state"""
        self.audio_buffer = []
        self.last_detection_time = 0
        self.logger.debug("Wake word detector reset")
    
    def add_wake_word(self, word: str):
        """Add new wake word"""
        if word.lower() not in self.wake_words:
            self.wake_words.append(word.lower())
            # Add pattern for the new word
            self.wake_word_patterns.append(f"\\b{re.escape(word.lower())}\\b")
            self.logger.info(f"Added wake word: {word}")
    
    def remove_wake_word(self, word: str):
        """Remove wake word"""
        word = word.lower()
        if word in self.wake_words:
            self.wake_words.remove(word)
            # Rebuild patterns
            self.wake_word_patterns = [
                r'\b(hey\s+)?gemma\b',
                r'\bgemma\b',
                r'\bhey\s+gemma\b'
            ]
            for w in self.wake_words:
                if w not in ["gemma", "hey gemma"]:
                    self.wake_word_patterns.append(f"\\b{re.escape(w)}\\b")
            self.logger.info(f"Removed wake word: {word}")