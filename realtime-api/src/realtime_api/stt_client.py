"""Async httpx client for Parakeet STT."""

from __future__ import annotations

import logging

import httpx

from .audio import client_pcm16_to_wav_16k
from .config import settings

log = logging.getLogger(__name__)


async def transcribe(pcm16_24khz: bytes, stt_url: str | None = None) -> str:
    """Send PCM16 24kHz audio to Parakeet STT and return the transcription text.

    Converts 24kHz PCM16 to 16kHz WAV before sending.
    """
    url = (stt_url or settings.stt_url).rstrip("/") + "/v1/audio/transcriptions"
    wav_data = client_pcm16_to_wav_16k(pcm16_24khz)

    async with httpx.AsyncClient(timeout=60.0) as client:
        resp = await client.post(
            url,
            data={"language": "en"},
            files={"file": ("audio.wav", wav_data, "audio/wav")},
        )

    if resp.status_code != 200:
        log.error("STT error %d: %s", resp.status_code, resp.text)
        return ""

    text = resp.json().get("text", "").strip()
    log.info("STT transcript: %s", text)
    return text
