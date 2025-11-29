import logging
import numpy as np
import torch

logger = logging.getLogger(__name__)


class SileroVAD:
    """Voice Activity Detector using Silero VAD
    
    Silero VAD is more robust to noise and non-speech sounds compared to WebRTC VAD.
    It uses a neural network model and returns a probability score.
    """
    
    def __init__(self, threshold: float = 0.5, sample_rate: int = 16000):
        """
        Initialize Silero VAD detector
        
        Args:
            threshold: Speech probability threshold (0.0-1.0). Higher = more conservative
            sample_rate: Audio sample rate in Hz (Silero supports 8000 and 16000)
        """
        self.sample_rate = sample_rate
        self.threshold = threshold
        
        # Silero VAD requires minimum chunk size
        # At 16kHz: minimum 512 samples (32ms), optimal 512, 1024, or 1536 samples
        # At 8kHz: minimum 256 samples (32ms), optimal 256, 512, or 768 samples
        if sample_rate == 16000:
            self.min_samples = 512  # 32ms at 16kHz
        elif sample_rate == 8000:
            self.min_samples = 256  # 32ms at 8kHz
        else:
            logger.warning(f"Silero VAD works best with 8000 or 16000 Hz, got {sample_rate}")
            self.min_samples = 512  # Default
        
        # Internal buffer to accumulate audio data
        self.buffer = np.array([], dtype=np.int16)
        self.last_result = False  # Track last speech detection result
        
        try:
            logger.info("Loading Silero VAD model from torch hub...")
            # Load Silero VAD model
            self.model, utils = torch.hub.load(
                repo_or_dir='snakers4/silero-vad',
                model='silero_vad',
                force_reload=False,
                onnx=False
            )
            
            # Extract utility functions
            (self.get_speech_timestamps,
             self.save_audio,
             self.read_audio,
             self.VADIterator,
             self.collect_chunks) = utils
            
            # Set model to eval mode
            self.model.eval()
            
            logger.info(f"Silero VAD initialized with threshold={threshold}, rate={sample_rate}Hz, min_samples={self.min_samples}")
            
        except Exception as e:
            logger.error(f"Failed to initialize Silero VAD: {e}")
            raise
    
    def is_speech(self, audio_data: bytes) -> bool:
        """
        Check if audio data contains speech using Silero VAD
        
        Buffers incoming audio until we have enough samples for the model.
        Silero requires EXACTLY 512 samples at 16kHz (or 256 at 8kHz).
        
        Args:
            audio_data: Raw audio data as bytes (int16 PCM)
            
        Returns:
            True if speech is detected (probability >= threshold), False otherwise
        """
        try:
            # Convert bytes to numpy array (int16)
            audio_int16 = np.frombuffer(audio_data, dtype=np.int16)
            
            # Add to buffer
            self.buffer = np.concatenate([self.buffer, audio_int16])
            
            # Check if we have enough samples
            if len(self.buffer) < self.min_samples:
                # Not enough data yet, return last known result
                logger.debug(f"Silero VAD: buffering {len(self.buffer)}/{self.min_samples} samples, returning last result: {self.last_result}")
                return self.last_result
            
            # Extract EXACTLY the required number of samples
            audio_chunk = self.buffer[:self.min_samples]
            
            # Keep remaining samples in buffer for next call
            self.buffer = self.buffer[self.min_samples:]
            
            # Convert to float32 normalized to [-1, 1]
            audio_float32 = audio_chunk.astype(np.float32) / 32768.0
            
            # Convert to torch tensor
            audio_tensor = torch.from_numpy(audio_float32)
            
            # Get speech probability
            with torch.no_grad():
                speech_prob = self.model(audio_tensor, self.sample_rate).item()
            
            result = speech_prob >= self.threshold
            
            # Update last result
            self.last_result = result
            
            # Log detailed info for debugging
            logger.debug(f"Silero VAD: processed {len(audio_float32)} samples, probability={speech_prob:.3f}, threshold={self.threshold}, result={'SPEECH' if result else 'SILENCE'}, buffer_remaining={len(self.buffer)}")
            
            return result
            
        except Exception as e:
            logger.error(f"Error in Silero VAD processing: {e} (audio_data length: {len(audio_data)} bytes, buffer size: {len(self.buffer)})")
            # Clear buffer on error
            self.buffer = np.array([], dtype=np.int16)
            return False
    
    def set_threshold(self, threshold: float):
        """
        Update speech detection threshold
        
        Args:
            threshold: New threshold value (0.0-1.0)
        """
        if not 0.0 <= threshold <= 1.0:
            raise ValueError("Threshold must be between 0.0 and 1.0")
        
        self.threshold = threshold
        logger.info(f"Silero VAD threshold updated to {threshold}")
