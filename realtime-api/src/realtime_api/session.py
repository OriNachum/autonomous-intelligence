"""Session state, conversation history, audio buffer."""

from __future__ import annotations

import asyncio
import base64
import logging
from dataclasses import dataclass, field

from .config import settings
from .protocol import (
    AECMode,
    AudioFormat,
    TurnDetectionType,
    gen_content_part_id,
    gen_item_id,
    gen_session_id,
)
from .vad import ServerVAD, VADConfig

log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Session config
# ---------------------------------------------------------------------------
@dataclass
class TurnDetectionConfig:
    type: str = "server_vad"
    threshold: float = 0.5
    silence_duration_ms: int = 600
    prefix_padding_ms: int = 300
    aec_mode: str = "none"

    @classmethod
    def from_dict(cls, d: dict) -> TurnDetectionConfig:
        return cls(
            type=d.get("type", "server_vad"),
            threshold=d.get("threshold", 0.5),
            silence_duration_ms=d.get("silence_duration_ms", 600),
            prefix_padding_ms=d.get("prefix_padding_ms", 300),
            aec_mode=d.get("aec_mode", "none"),
        )


@dataclass
class SessionConfig:
    modalities: list[str] = field(default_factory=lambda: ["text", "audio"])
    instructions: str = ""
    voice: str = field(default_factory=lambda: settings.default_voice)
    input_audio_format: str = AudioFormat.PCM16
    output_audio_format: str = AudioFormat.PCM16
    temperature: float = 0.8
    tts_mode: str = "whole"  # "sentence" or "whole"
    turn_detection: TurnDetectionConfig | None = field(
        default_factory=lambda: TurnDetectionConfig(
            threshold=settings.vad_threshold,
            silence_duration_ms=settings.vad_silence_ms,
            prefix_padding_ms=settings.vad_prefix_padding_ms,
            aec_mode=settings.default_aec_mode,
        )
        if settings.default_turn_detection == "server_vad"
        else None
    )

    def to_dict(self) -> dict:
        d: dict = {
            "modalities": self.modalities,
            "instructions": self.instructions,
            "voice": self.voice,
            "input_audio_format": self.input_audio_format,
            "output_audio_format": self.output_audio_format,
            "temperature": self.temperature,
            "tts_mode": self.tts_mode,
        }
        if self.turn_detection:
            d["turn_detection"] = {
                "type": self.turn_detection.type,
                "threshold": self.turn_detection.threshold,
                "silence_duration_ms": self.turn_detection.silence_duration_ms,
                "prefix_padding_ms": self.turn_detection.prefix_padding_ms,
                "aec_mode": self.turn_detection.aec_mode,
            }
        else:
            d["turn_detection"] = None
        return d

    def update_from_dict(self, d: dict):
        """Update config from a session.update event dict."""
        if "modalities" in d:
            self.modalities = d["modalities"]
        if "instructions" in d:
            self.instructions = d["instructions"]
        if "voice" in d:
            self.voice = d["voice"]
        if "input_audio_format" in d:
            self.input_audio_format = d["input_audio_format"]
        if "output_audio_format" in d:
            self.output_audio_format = d["output_audio_format"]
        if "temperature" in d:
            self.temperature = d["temperature"]
        if "tts_mode" in d:
            self.tts_mode = d["tts_mode"]
        if "turn_detection" in d:
            td = d["turn_detection"]
            if td is None:
                self.turn_detection = None
            else:
                self.turn_detection = TurnDetectionConfig.from_dict(td)


# ---------------------------------------------------------------------------
# Audio buffer
# ---------------------------------------------------------------------------
class AudioBuffer:
    """Accumulates base64-encoded PCM16 chunks from the client."""

    def __init__(self):
        self._chunks: list[bytes] = []
        self._total_bytes = 0

    def append(self, audio_b64: str):
        """Append base64-encoded PCM16 audio."""
        decoded = base64.b64decode(audio_b64)
        self._chunks.append(decoded)
        self._total_bytes += len(decoded)

    def append_raw(self, pcm_bytes: bytes):
        """Append raw PCM16 bytes directly."""
        self._chunks.append(pcm_bytes)
        self._total_bytes += len(pcm_bytes)

    def commit(self) -> bytes:
        """Return all accumulated audio as raw PCM16 bytes and clear the buffer."""
        data = b"".join(self._chunks)
        self.clear()
        return data

    def clear(self):
        self._chunks.clear()
        self._total_bytes = 0

    @property
    def total_bytes(self) -> int:
        return self._total_bytes

    @property
    def is_empty(self) -> bool:
        return self._total_bytes == 0


# ---------------------------------------------------------------------------
# Conversation item tracking
# ---------------------------------------------------------------------------
@dataclass
class ConversationItem:
    id: str
    role: str  # "user" or "assistant"
    content: list[dict]  # [{type: "text", text: "..."} or {type: "audio", ...}]

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "object": "realtime.item",
            "type": "message",
            "role": self.role,
            "content": self.content,
        }


class Conversation:
    """Tracks conversation items and converts to chat completion messages."""

    def __init__(self):
        self._items: list[ConversationItem] = []

    def add_user_message(self, text: str, item_id: str | None = None) -> ConversationItem:
        item = ConversationItem(
            id=item_id or gen_item_id(),
            role="user",
            content=[{"type": "input_text", "text": text}],
        )
        self._items.append(item)
        return item

    def add_assistant_message(self, text: str, item_id: str | None = None) -> ConversationItem:
        item = ConversationItem(
            id=item_id or gen_item_id(),
            role="assistant",
            content=[{"type": "text", "text": text}],
        )
        self._items.append(item)
        return item

    def to_chat_messages(self, system_instructions: str = "") -> list[dict]:
        """Convert conversation to OpenAI chat completion messages format."""
        messages: list[dict] = []
        if system_instructions:
            messages.append({"role": "system", "content": system_instructions})
        for item in self._items:
            text_parts = [
                c.get("text", "") for c in item.content if c.get("type") in ("text", "input_text")
            ]
            if text_parts:
                messages.append({"role": item.role, "content": " ".join(text_parts)})
        return messages

    @property
    def items(self) -> list[ConversationItem]:
        return list(self._items)


# ---------------------------------------------------------------------------
# Session
# ---------------------------------------------------------------------------
class Session:
    """Holds all state for a single WebSocket connection."""

    def __init__(self):
        self.id = gen_session_id()
        self.config = SessionConfig()
        self.conversation = Conversation()
        self.audio_buffer = AudioBuffer()
        self.send_queue: asyncio.Queue[dict] = asyncio.Queue()
        self.cancel_event = asyncio.Event()
        self.is_speaking = False
        self.current_response_text = ""  # accumulates assistant text for barge-in context
        self._vad: ServerVAD | None = None
        self._response_task: asyncio.Task | None = None
        self._pipeline_pending = False  # set synchronously in auto_commit before task creation

    @property
    def vad(self) -> ServerVAD | None:
        return self._vad

    def init_vad(self):
        """Initialize or re-initialize VAD based on current config."""
        td = self.config.turn_detection
        if td and td.type == "server_vad":
            vad_config = VADConfig(
                threshold=td.threshold,
                silence_duration_ms=td.silence_duration_ms,
                prefix_padding_ms=td.prefix_padding_ms,
            )
            aec = AECMode.AEC if td.aec_mode == "aec" else AECMode.NONE
            self._vad = ServerVAD(config=vad_config, aec_mode=aec)
        else:
            self._vad = None

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "object": "realtime.session",
            **self.config.to_dict(),
        }

    async def send(self, event: dict):
        """Queue a server event for sending to the client."""
        await self.send_queue.put(event)
