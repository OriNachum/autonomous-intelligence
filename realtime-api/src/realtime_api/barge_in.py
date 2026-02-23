"""LLM-based intelligent interruption decision for AEC mode barge-in."""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field

from .config import settings
from .llm_client import quick_decision
from .protocol import CLIENT_SAMPLE_RATE, BYTES_PER_SAMPLE
from .stt_client import transcribe

log = logging.getLogger(__name__)

BARGE_IN_SYSTEM_PROMPT = """\
You are a conversation flow controller. The assistant is currently speaking.
The user just said something. Decide: should the assistant STOP speaking and listen,
or CONTINUE speaking (the user is just acknowledging/backchanneling)?
Reply with exactly one word: STOP or CONTINUE.
"""


@dataclass
class BargeInEvaluator:
    """Evaluates whether detected speech during response playback is a real
    interruption or just a backchannel acknowledgement.

    Flow:
    1. Accumulate audio for a short decision window (barge_in_window_ms)
    2. Quick-transcribe the snippet via Parakeet STT (1-3 words)
    3. Fast LLM call to decide STOP or CONTINUE
    """

    window_ms: int = field(default_factory=lambda: settings.barge_in_window_ms)
    _buffer: bytearray = field(default_factory=bytearray, init=False)
    _collecting: bool = field(default=False, init=False)

    @property
    def window_bytes(self) -> int:
        """Number of bytes needed for the decision window at 24kHz PCM16."""
        return int(self.window_ms * CLIENT_SAMPLE_RATE * BYTES_PER_SAMPLE / 1000)

    def start_collecting(self):
        """Start collecting audio for barge-in evaluation."""
        self._buffer = bytearray()
        self._collecting = True

    def feed_audio(self, pcm16_24khz: bytes) -> bool:
        """Feed audio data. Returns True when enough audio has been collected."""
        if not self._collecting:
            return False
        self._buffer.extend(pcm16_24khz)
        return len(self._buffer) >= self.window_bytes

    def stop_collecting(self) -> bytes:
        """Stop collecting and return the accumulated audio."""
        self._collecting = False
        audio = bytes(self._buffer)
        self._buffer = bytearray()
        return audio

    @property
    def is_collecting(self) -> bool:
        return self._collecting

    async def evaluate(
        self,
        audio_pcm16_24khz: bytes,
        assistant_last_text: str,
    ) -> str:
        """Evaluate whether the detected speech is a real interruption.

        Args:
            audio_pcm16_24khz: Short audio snippet (PCM16 24kHz) from the user.
            assistant_last_text: Last ~50 tokens of the assistant's current response.

        Returns:
            "STOP" if the user is interrupting, "CONTINUE" if backchanneling.
        """
        # Quick-transcribe the snippet
        transcript = await transcribe(audio_pcm16_24khz)
        if not transcript or not any(c.isalnum() for c in transcript):
            log.info("Barge-in: empty transcript, defaulting to CONTINUE")
            return "CONTINUE"

        log.info("Barge-in transcript: '%s'", transcript)

        # Truncate assistant text to last ~50 tokens (~200 chars)
        assistant_context = assistant_last_text[-200:] if assistant_last_text else ""

        user_content = (
            f'Assistant\'s last words: "...{assistant_context}..."\n'
            f'User said: "{transcript}"'
        )

        decision = await quick_decision(
            BARGE_IN_SYSTEM_PROMPT,
            user_content,
        )

        # Normalize — accept STOP or CONTINUE, default to STOP for safety
        if "CONTINUE" in decision:
            log.info("Barge-in decision: CONTINUE (backchannel: '%s')", transcript)
            return "CONTINUE"
        else:
            log.info("Barge-in decision: STOP (interruption: '%s')", transcript)
            return "STOP"
