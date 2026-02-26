"""Async httpx client for Magpie TTS — full-read per sentence."""

from __future__ import annotations

import asyncio
import logging
import re
from xml.sax.saxutils import escape as xml_escape

import httpx

from .config import settings
from .protocol import TTS_SAMPLE_RATE, VOICE_PREFIX, resolve_voice

log = logging.getLogger(__name__)

# Regex to strip emoji (Supplementary Multilingual Plane + common emoji ranges)
_EMOJI_RE = re.compile(
    "[\U0001F600-\U0001F64F"  # emoticons
    "\U0001F300-\U0001F5FF"   # symbols & pictographs
    "\U0001F680-\U0001F6FF"   # transport & map
    "\U0001F1E0-\U0001F1FF"   # flags
    "\U00002702-\U000027B0"   # dingbats
    "\U0000FE00-\U0000FE0F"   # variation selectors
    "\U0000200D"              # zero-width joiner
    "\U000024C2-\U0001F251"
    "]+",
    flags=re.UNICODE,
)

# Markdown-style formatting
_MARKDOWN_RE = re.compile(r"[*_~`#]")

# Module-level client — reused across requests for connection pooling
_client: httpx.AsyncClient | None = None


def _get_client() -> httpx.AsyncClient:
    global _client
    if _client is None or _client.is_closed:
        _client = httpx.AsyncClient(timeout=httpx.Timeout(120.0, read=60.0))
    return _client


def _clean_for_tts(text: str) -> str:
    """Strip emoji, markdown, and normalize whitespace for TTS input."""
    text = _EMOJI_RE.sub(" ", text)
    text = _MARKDOWN_RE.sub("", text)
    # Collapse whitespace / newlines
    text = re.sub(r"\s+", " ", text).strip()
    return text


async def synthesize(
    text: str,
    voice: str | None = None,
    speed: int | None = None,
    tts_url: str | None = None,
    cancel_event: asyncio.Event | None = None,
) -> bytes:
    """Synthesize text via Magpie TTS, returning complete PCM16 audio at 22050Hz.

    Reads the full TTS response before returning to avoid truncation from
    event-loop contention during async streaming.

    Returns:
        Raw PCM16 bytes at 22050Hz (empty bytes if nothing to synthesize).
    """
    url = (tts_url or settings.tts_url).rstrip("/") + "/v1/audio/synthesize_online"
    full_voice = resolve_voice(voice or settings.default_voice)
    spd = speed if speed is not None else settings.tts_speed

    # Clean text: strip emoji, markdown, normalize whitespace
    clean = _clean_for_tts(text)
    if not clean:
        log.debug("[TTS] skipping empty text after cleanup (original: %s)", text[:40])
        return b""

    # Wrap in SSML prosody if speed != 100; xml_escape prevents broken markup
    tts_text = clean
    if spd != 100:
        tts_text = f'<speak><prosody rate="{spd}%">{xml_escape(clean)}</prosody></speak>'

    try:
        client = _get_client()
        resp = await client.post(
            url,
            data={
                "text": tts_text,
                "language": "en-US",
                "voice": full_voice,
                "encoding": "LINEAR_PCM",
                "sample_rate_hz": str(TTS_SAMPLE_RATE),
            },
        )
        if resp.status_code != 200:
            log.error("[TTS] error %d for text: %s", resp.status_code, clean[:60])
            return b""

        pcm_data = resp.content
        duration = len(pcm_data) / 2 / TTS_SAMPLE_RATE
        log.info("[TTS] synthesized %d bytes (%.2fs) for: %s", len(pcm_data), duration, clean[:60])
        return pcm_data

    except httpx.ConnectError:
        log.error("[TTS] cannot connect to %s", tts_url or settings.tts_url)
        return b""
    except Exception as e:
        log.error("[TTS] error: %s", e)
        return b""


# Keep backward-compat alias for any callers using the streaming API
async def synthesize_stream(
    text: str,
    voice: str | None = None,
    speed: int | None = None,
    tts_url: str | None = None,
    cancel_event: asyncio.Event | None = None,
):
    """Compatibility wrapper — calls synthesize() and yields the result as a single chunk."""
    data = await synthesize(text, voice=voice, speed=speed, tts_url=tts_url, cancel_event=cancel_event)
    if data:
        yield data
