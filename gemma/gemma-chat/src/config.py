"""Configuration settings for Gemma"""

import os
from dataclasses import dataclass
from typing import Optional

@dataclass
class Config:
    # Event System
    EVENT_SOCKET_PATH: str = "/tmp/gemma_events.sock"
    EVENT_BUFFER_SIZE: int = 4096
    
    # Camera Processing
    CAMERA_DEVICE: int = 0
    CAMERA_WIDTH: int = 640
    CAMERA_HEIGHT: int = 480
    CAMERA_FPS: int = 30
    YOLO_MODEL_PATH: str = "yolov6n.pt"
    DETECTION_CONFIDENCE: float = 0.5
    
    # Audio Processing
    AUDIO_SAMPLE_RATE: int = 16000
    AUDIO_CHANNELS: int = 1
    AUDIO_CHUNK_SIZE: int = 1024
    VAD_MODEL_PATH: str = "silero_vad"
    WAKE_WORDS: list = ("Gemma", "Hey Gemma")
    
    # AI Model API
    API_URL: str = "http://localhost:8000"
    MODEL_NAME: str = "gemma3n"
    MAX_HISTORY: int = 20
    MAX_NEW_TOKENS: int = 100
    TEMPERATURE: float = 0.7
    RESPONSE_TARGET_MS: int = 400
    
    # Memory System
    IMMEDIATE_MEMORY_SIZE: int = 100
    MILVUS_HOST: str = "localhost"
    MILVUS_PORT: int = 19530
    NEO4J_URI: str = "bolt://localhost:7687"
    NEO4J_USER: str = "neo4j"
    NEO4J_PASSWORD: str = "password"
    
    # TTS
    TTS_ENGINE: str = "kokoro"
    TTS_QUEUE_MAX_SIZE: int = 10
    TTS_MAX_TOKENS: int = 500
    
    # Logging
    LOG_LEVEL: str = "INFO"
    LOG_FORMAT: str = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    
    @classmethod
    def from_env(cls) -> "Config":
        """Load configuration from environment variables"""
        config = cls()
        
        # Update from environment variables
        for field_name, field_value in config.__dict__.items():
            env_value = os.getenv(f"GEMMA_{field_name}")
            if env_value is not None:
                if isinstance(field_value, int):
                    setattr(config, field_name, int(env_value))
                elif isinstance(field_value, float):
                    setattr(config, field_name, float(env_value))
                elif isinstance(field_value, bool):
                    setattr(config, field_name, env_value.lower() in ("true", "1", "yes"))
                elif isinstance(field_value, list):
                    setattr(config, field_name, env_value.split(","))
                else:
                    setattr(config, field_name, env_value)
        
        return config