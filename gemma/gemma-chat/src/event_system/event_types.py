"""Event types and data structures for Gemma"""

from enum import Enum
from dataclasses import dataclass, asdict
from typing import Dict, Any, Optional, List
import json
import time

class EventType(Enum):
    # Camera events
    CAMERA_FRAME = "camera_frame"
    OBJECT_DETECTED = "object_detected"
    OBJECT_DISAPPEARED = "object_disappeared"
    
    # Audio events
    SPEECH_DETECTED = "speech_detected"
    WAKE_WORD_DETECTED = "wake_word_detected"
    AUDIO_FRAME = "audio_frame"
    
    # Text events
    TEXT_INPUT = "text_input"
    
    # TTS events
    QUEUE_SENTENCES = "queue_sentences"
    RESET_QUEUE = "reset_queue"
    TTS_FINISHED = "tts_finished"
    
    # Memory events
    FACT_DISTILLED = "fact_distilled"
    MEMORY_RETRIEVED = "memory_retrieved"
    
    # System events
    SYSTEM_READY = "system_ready"
    SYSTEM_SHUTDOWN = "system_shutdown"
    ERROR = "error"

@dataclass
class GemmaEvent:
    """Base event class for Gemma system"""
    event_type: EventType
    timestamp: float
    data: Dict[str, Any]
    priority: int = 0  # Higher values = higher priority
    source: str = "unknown"
    
    def __post_init__(self):
        if self.timestamp == 0:
            self.timestamp = time.time()
    
    def to_json(self) -> str:
        """Serialize event to JSON string"""
        data = asdict(self)
        data['event_type'] = self.event_type.value
        return json.dumps(data)
    
    @classmethod
    def from_json(cls, json_str: str) -> "GemmaEvent":
        """Deserialize event from JSON string"""
        data = json.loads(json_str)
        data['event_type'] = EventType(data['event_type'])
        return cls(**data)

@dataclass
class CameraEvent(GemmaEvent):
    """Camera-specific event"""
    def __init__(self, event_type: EventType, frame_data: Optional[bytes] = None, 
                 detections: Optional[List[Dict]] = None, **kwargs):
        data = {
            'frame_data': frame_data,
            'detections': detections or []
        }
        super().__init__(event_type, time.time(), data, **kwargs)

@dataclass
class AudioEvent(GemmaEvent):
    """Audio-specific event"""
    def __init__(self, event_type: EventType, audio_data: Optional[bytes] = None,
                 wake_word: Optional[str] = None, confidence: float = 0.0, **kwargs):
        data = {
            'audio_data': audio_data,
            'wake_word': wake_word,
            'confidence': confidence
        }
        super().__init__(event_type, time.time(), data, **kwargs)

@dataclass
class TextEvent(GemmaEvent):
    """Text-specific event"""
    def __init__(self, event_type: EventType, text: str, **kwargs):
        data = {'text': text}
        super().__init__(event_type, time.time(), data, **kwargs)

@dataclass
class TTSEvent(GemmaEvent):
    """TTS-specific event"""
    def __init__(self, event_type: EventType, sentences: Optional[List[str]] = None, **kwargs):
        data = {'sentences': sentences or []}
        super().__init__(event_type, time.time(), data, **kwargs)