"""Pydantic Settings — configuration from environment variables."""

from __future__ import annotations

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # Service URLs
    tts_url: str = "http://magpie-tts:8091"
    stt_url: str = "http://parakeet-stt:9002"

    # LLM backend (OpenAI-compatible)
    openai_base_url: str = "http://host.docker.internal:8000"
    openai_api_key: str = "EMPTY"
    openai_model: str = "default"

    # TTS defaults
    default_voice: str = "Mia.Calm"
    tts_speed: int = 125

    # VAD settings
    vad_threshold: float = 0.5
    vad_silence_ms: int = 600
    vad_prefix_padding_ms: int = 300

    # Turn detection
    default_turn_detection: str = "server_vad"
    default_aec_mode: str = "none"

    # Barge-in settings
    barge_in_window_ms: int = 750
    barge_in_model: str | None = None

    # Server
    host: str = "0.0.0.0"
    port: int = 8080


settings = Settings()
