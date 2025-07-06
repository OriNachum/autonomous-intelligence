"""Voice Activity Detection using SileroVAD"""

import logging
import numpy as np
import torch
from typing import Optional, List, Tuple
import time

try:
    import silero_vad
    SILERO_AVAILABLE = True
except ImportError:
    SILERO_AVAILABLE = False
    logging.warning("SileroVAD not available, using mock VAD")

class VADDetector:
    """Voice Activity Detection using SileroVAD"""
    
    def __init__(self, model_path: str = "silero_vad", sample_rate: int = 16000):
        self.model_path = model_path
        self.sample_rate = sample_rate
        self.logger = logging.getLogger(__name__)
        
        # VAD model
        self.model = None
        self.utils = None
        
        # Processing state
        self.is_speech_active = False
        self.speech_start_time = 0
        self.speech_end_time = 0
        self.min_speech_duration = 0.5  # seconds
        self.min_silence_duration = 0.3  # seconds
        
        # Audio buffering
        self.audio_buffer = []
        self.buffer_size = sample_rate * 2  # 2 seconds
        
        # Statistics
        self.total_speech_time = 0
        self.speech_segments = []
        
        # Initialize model
        self._load_model()
    
    def _load_model(self):
        """Load SileroVAD model"""
        try:
            if SILERO_AVAILABLE:
                self.model, self.utils = silero_vad.load_silero_vad()
                self.logger.info("SileroVAD model loaded successfully")
            else:
                self.logger.warning("SileroVAD not available, using mock VAD")
        except Exception as e:
            self.logger.error(f"Error loading SileroVAD model: {e}")
            self.model = None
    
    def process_audio(self, audio_data: np.ndarray) -> Tuple[bool, float]:
        """Process audio data and return VAD result"""
        if self.model is None:
            return self._mock_vad(audio_data)
        
        try:
            # Ensure audio is float32 and normalized
            if audio_data.dtype != np.float32:
                audio_data = audio_data.astype(np.float32)
            
            # Normalize audio
            if np.max(np.abs(audio_data)) > 0:
                audio_data = audio_data / np.max(np.abs(audio_data))
            
            # Convert to tensor
            audio_tensor = torch.from_numpy(audio_data)
            
            # Get VAD prediction
            speech_prob = self.model(audio_tensor, self.sample_rate).item()
            
            # Update speech state
            is_speech = speech_prob > 0.5
            
            return is_speech, speech_prob
            
        except Exception as e:
            self.logger.error(f"Error in VAD processing: {e}")
            return False, 0.0
    
    def _mock_vad(self, audio_data: np.ndarray) -> Tuple[bool, float]:
        """Mock VAD for testing when SileroVAD is not available"""
        # Simple energy-based VAD
        energy = np.sqrt(np.mean(audio_data ** 2))
        threshold = 0.01
        
        is_speech = energy > threshold
        confidence = min(energy / threshold, 1.0)
        
        return is_speech, confidence
    
    def update_speech_state(self, is_speech: bool, confidence: float) -> Optional[str]:
        """Update speech state and return events"""
        current_time = time.time()
        
        if is_speech and not self.is_speech_active:
            # Speech started
            self.speech_start_time = current_time
            self.is_speech_active = True
            return "speech_started"
            
        elif not is_speech and self.is_speech_active:
            # Potential speech end
            silence_duration = current_time - self.speech_start_time
            
            if silence_duration >= self.min_silence_duration:
                # Speech ended
                self.speech_end_time = current_time
                speech_duration = self.speech_end_time - self.speech_start_time
                
                if speech_duration >= self.min_speech_duration:
                    # Valid speech segment
                    self.speech_segments.append({
                        'start': self.speech_start_time,
                        'end': self.speech_end_time,
                        'duration': speech_duration
                    })
                    self.total_speech_time += speech_duration
                    
                    self.is_speech_active = False
                    return "speech_ended"
                else:
                    # Too short, continue listening
                    return None
            else:
                # Still in potential speech
                return None
        
        return None
    
    def add_to_buffer(self, audio_data: np.ndarray):
        """Add audio data to buffer"""
        self.audio_buffer.extend(audio_data.tolist())
        
        # Trim buffer if too large
        if len(self.audio_buffer) > self.buffer_size:
            self.audio_buffer = self.audio_buffer[-self.buffer_size:]
    
    def get_speech_audio(self) -> Optional[np.ndarray]:
        """Get audio data from speech segment"""
        if not self.is_speech_active or not self.audio_buffer:
            return None
        
        # Return recent audio from buffer
        return np.array(self.audio_buffer[-int(self.sample_rate * 2):])
    
    def get_statistics(self) -> dict:
        """Get VAD statistics"""
        return {
            'total_speech_time': self.total_speech_time,
            'speech_segments': len(self.speech_segments),
            'is_speech_active': self.is_speech_active,
            'buffer_size': len(self.audio_buffer),
            'recent_segments': self.speech_segments[-10:] if self.speech_segments else []
        }
    
    def reset(self):
        """Reset VAD state"""
        self.is_speech_active = False
        self.speech_start_time = 0
        self.speech_end_time = 0
        self.audio_buffer = []
        self.logger.debug("VAD state reset")