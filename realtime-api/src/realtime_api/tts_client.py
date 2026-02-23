"""Async streaming httpx client for Magpie TTS."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import AsyncIterator

import httpx

from .config import settings
from .protocol import TTS_SAMPLE_RATE, VOICE_PREFIX, resolve_voice

log = logging.getLogger(__name__)


async def synthesize_stream(
    text: str,
    voice: str | None = None,
    speed: int | None = None,
    tts_url: str | None = None,
    cancel_event: asyncio.Event | None = None,
) -> AsyncIterator[bytes]:
    """Stream-synthesize text via Magpie TTS, yielding raw PCM16 chunks at 22050Hz.

    Args:
        text: Text to synthesize (may include SSML).
        voice: Voice name (OpenAI or Magpie). Defaults to settings.default_voice.
        speed: Speech speed percentage. Defaults to settings.tts_speed.
        tts_url: Override TTS service URL.
        cancel_event: If set, stop streaming.

    Yields:
        Raw PCM16 bytes at 22050Hz.
    """
    url = (tts_url or settings.tts_url).rstrip("/") + "/v1/audio/synthesize_online"
    full_voice = resolve_voice(voice or settings.default_voice)
    spd = speed if speed is not None else settings.tts_speed

    # Wrap in SSML prosody if speed != 100
    tts_text = text
    if spd != 100:
        tts_text = f'<speak><prosody rate="{spd}%">{text}</prosody></speak>'

    try:
        async with httpx.AsyncClient(timeout=120.0) as client:
            async with client.stream(
                "POST",
                url,
                data={
                    "text": tts_text,
                    "language": "en-US",
                    "voice": full_voice,
                    "encoding": "LINEAR_PCM",
                    "sample_rate_hz": str(TTS_SAMPLE_RATE),
                },
            ) as resp:
                if resp.status_code != 200:
                    log.error("TTS error %d", resp.status_code)
                    return

                async for chunk in resp.aiter_bytes(4096):
                    if cancel_event and cancel_event.is_set():
                        break
                    yield chunk

    except httpx.ConnectError:
        log.error("Cannot connect to TTS at %s", tts_url or settings.tts_url)
    except Exception as e:
        log.error("TTS streaming error: %s", e)
