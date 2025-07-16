"""Sound processing module with VAD and wake word detection"""

from .sound_processor import SoundProcessor
from .vad_detector import VADDetector
from .wake_word_detector import WakeWordDetector

__all__ = ["SoundProcessor", "VADDetector", "WakeWordDetector"]