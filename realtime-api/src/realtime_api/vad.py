"""Silero VAD wrapper + turn detection state machine."""

from __future__ import annotations

import logging
from collections import deque
from dataclasses import dataclass, field
from enum import Enum, auto

import numpy as np

from .audio import client_pcm16_to_vad_float32, resample_pcm16
from .protocol import (
    CLIENT_SAMPLE_RATE,
    VAD_CHUNK_MS,
    VAD_CHUNK_SAMPLES,
    VAD_SAMPLE_RATE,
    AECMode,
)

log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# VAD events emitted by the state machine
# ---------------------------------------------------------------------------
class VADEventType(Enum):
    SPEECH_STARTED = auto()
    SPEECH_STOPPED = auto()


@dataclass
class VADEvent:
    type: VADEventType
    audio_ms: int = 0
    audio_bytes: bytes = b""  # accumulated speech audio (PCM16 24kHz) on SPEECH_STOPPED


# ---------------------------------------------------------------------------
# Silero VAD model wrapper
# ---------------------------------------------------------------------------
class SileroVAD:
    """Thin wrapper around silero-vad."""

    def __init__(self):
        import torch

        self._torch = torch
        model, _ = torch.hub.load("snakers4/silero-vad", "silero_vad", trust_repo=True)
        self.model = model
        self.reset()

    def reset(self):
        self.model.reset_states()

    def probability(self, float32_samples: np.ndarray) -> float:
        """Return speech probability for a chunk of float32 samples at 16kHz."""
        tensor = self._torch.from_numpy(float32_samples)
        with self._torch.no_grad():
            prob = self.model(tensor, VAD_SAMPLE_RATE).item()
        return prob


# ---------------------------------------------------------------------------
# Turn detection state machine
# ---------------------------------------------------------------------------
class _State(Enum):
    IDLE = auto()
    LISTENING = auto()


@dataclass
class VADConfig:
    threshold: float = 0.5
    silence_duration_ms: int = 600
    prefix_padding_ms: int = 300
    start_chunks: int = 3  # consecutive chunks above threshold to trigger


@dataclass
class ServerVAD:
    """Silero VAD + turn detection state machine.

    Processes PCM16 24kHz audio from the client and emits speech_started/speech_stopped events.
    """

    config: VADConfig = field(default_factory=VADConfig)
    aec_mode: AECMode = AECMode.NONE
    is_speaking: bool = False  # True when assistant is playing audio

    def __post_init__(self):
        self._vad = SileroVAD()
        self._state = _State.IDLE
        pre_roll_chunks = max(1, self.config.prefix_padding_ms // VAD_CHUNK_MS)
        self._pre_roll: deque[bytes] = deque(maxlen=pre_roll_chunks)
        self._speech_buffer: bytearray = bytearray()
        self._start_count = 0
        self._silence_ms = 0
        self._audio_cursor_ms = 0
        self._speech_start_ms = 0
        # Residual buffer for incomplete VAD chunks
        self._residual = b""

    def reset(self):
        """Reset all state."""
        self._vad.reset()
        self._state = _State.IDLE
        self._pre_roll.clear()
        self._speech_buffer = bytearray()
        self._start_count = 0
        self._silence_ms = 0
        self._residual = b""

    def process_chunk(self, pcm16_24khz: bytes) -> list[VADEvent]:
        """Process audio chunk (PCM16 24kHz), return VAD events."""
        # Echo gate: if assistant is speaking and non-AEC mode, discard audio
        if self.is_speaking and self.aec_mode == AECMode.NONE:
            return []

        # Prepend any residual from previous call
        data = self._residual + pcm16_24khz
        self._residual = b""

        # Resample entire buffer from 24kHz to 16kHz for VAD
        resampled = resample_pcm16(data, CLIENT_SAMPLE_RATE, VAD_SAMPLE_RATE)
        samples_16k = np.frombuffer(resampled, dtype=np.int16)

        events: list[VADEvent] = []
        chunk_size = VAD_CHUNK_SAMPLES

        i = 0
        while i + chunk_size <= len(samples_16k):
            chunk_samples = samples_16k[i : i + chunk_size]
            float_chunk = chunk_samples.astype(np.float32) / 32768.0
            prob = self._vad.probability(float_chunk)

            # Calculate how many bytes of 24kHz input this chunk corresponds to
            input_bytes_per_vad_chunk = int(chunk_size * CLIENT_SAMPLE_RATE / VAD_SAMPLE_RATE) * 2
            # Slice the corresponding 24kHz PCM bytes for buffering
            src_start = int(i * CLIENT_SAMPLE_RATE / VAD_SAMPLE_RATE) * 2
            src_end = src_start + input_bytes_per_vad_chunk
            chunk_24k = data[src_start:src_end]

            evts = self._update_state(prob, chunk_24k)
            events.extend(evts)
            self._audio_cursor_ms += VAD_CHUNK_MS
            i += chunk_size

        # Save leftover samples as residual (convert back to 24kHz byte count)
        leftover_16k = len(samples_16k) - i
        if leftover_16k > 0:
            leftover_24k_bytes = int(leftover_16k * CLIENT_SAMPLE_RATE / VAD_SAMPLE_RATE) * 2
            used_24k_bytes = int(i * CLIENT_SAMPLE_RATE / VAD_SAMPLE_RATE) * 2
            self._residual = data[used_24k_bytes:]

        return events

    def _update_state(self, prob: float, chunk_24k_bytes: bytes) -> list[VADEvent]:
        events: list[VADEvent] = []

        if self._state == _State.IDLE:
            self._pre_roll.append(chunk_24k_bytes)
            if prob >= self.config.threshold:
                self._start_count += 1
                if self._start_count >= self.config.start_chunks:
                    # Speech started
                    self._state = _State.LISTENING
                    self._speech_start_ms = self._audio_cursor_ms
                    # Include pre-roll audio
                    self._speech_buffer = bytearray()
                    for buf in self._pre_roll:
                        self._speech_buffer.extend(buf)
                    self._pre_roll.clear()
                    self._silence_ms = 0
                    events.append(
                        VADEvent(type=VADEventType.SPEECH_STARTED, audio_ms=self._speech_start_ms)
                    )
            else:
                self._start_count = 0

        elif self._state == _State.LISTENING:
            self._speech_buffer.extend(chunk_24k_bytes)
            if prob >= self.config.threshold * 0.6:  # Use lower threshold for end detection
                self._silence_ms = 0
            else:
                self._silence_ms += VAD_CHUNK_MS
                if self._silence_ms >= self.config.silence_duration_ms:
                    # Speech stopped — emit with accumulated audio
                    audio_bytes = bytes(self._speech_buffer)
                    self._speech_buffer = bytearray()
                    self._state = _State.IDLE
                    self._start_count = 0
                    self._silence_ms = 0
                    self._vad.reset()
                    events.append(
                        VADEvent(
                            type=VADEventType.SPEECH_STOPPED,
                            audio_ms=self._audio_cursor_ms,
                            audio_bytes=audio_bytes,
                        )
                    )

        return events
