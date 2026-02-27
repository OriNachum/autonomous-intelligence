"""Async httpx client for Magpie TTS — full-read per sentence."""

from __future__ import annotations

import asyncio
import logging
import re
import time
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

# Concurrency gate — limits parallel TTS requests across all sessions
_tts_semaphore: asyncio.Semaphore | None = None


def _get_client() -> httpx.AsyncClient:
    global _client
    if _client is None or _client.is_closed:
        _client = httpx.AsyncClient(timeout=httpx.Timeout(120.0, read=60.0))
    return _client


def _get_semaphore() -> asyncio.Semaphore:
    global _tts_semaphore
    if _tts_semaphore is None:
        _tts_semaphore = asyncio.Semaphore(settings.tts_concurrency)
        log.info("[TTS] concurrency gate: max %d parallel requests", settings.tts_concurrency)
    return _tts_semaphore


def _clean_for_tts(text: str) -> str:
    """Strip emoji, markdown, dashes, quotes and normalize for TTS input."""
    text = _EMOJI_RE.sub(" ", text)
    text = _MARKDOWN_RE.sub("", text)
    # Em-dash / en-dash → comma (natural pause; raw dashes confuse TTS)
    text = text.replace("\u2014", ", ")
    text = text.replace("\u2013", ", ")
    # Curly single quotes / apostrophes → ASCII apostrophe (preserves contractions)
    text = text.replace("\u2018", "'")
    text = text.replace("\u2019", "'")
    # Strip double-quotes (TTS doesn't need to voice them)
    text = re.sub(r'["\u201c\u201d]', "", text)
    # Remove markdown list markers at line start:  - item  /  1. item
    text = re.sub(r"(?m)^\s*-\s+", " ", text)
    text = re.sub(r"(?m)^\s*\d+[.)]\s+", " ", text)
    # Collapse whitespace / newlines
    text = re.sub(r"\s+", " ", text).strip()
    return text


# ---------------------------------------------------------------------------
# Punctuation-aware pause helpers
# ---------------------------------------------------------------------------

def _insert_ssml_breaks(text: str) -> str:
    """Insert SSML <break> tags at internal punctuation points.

    Call on xml_escape'd text — the break tags are injected *after* escaping
    so they remain valid SSML elements inside <speak>/<prosody>.
    """
    # Ellipsis (three dots or unicode) — must come before comma/period patterns
    text = re.sub(r"\.\.\.\s+", '... <break time="400ms"/> ', text)
    text = re.sub(r"\u2026\s*", '\u2026 <break time="400ms"/> ', text)

    # Em dash — (U+2014), optionally surrounded by spaces
    text = re.sub(r"\s*\u2014\s*", ' <break time="250ms"/> ', text)

    # En dash – (U+2013), optionally surrounded by spaces
    text = re.sub(r"\s*\u2013\s*", ' <break time="150ms"/> ', text)

    # Space-hyphen-space (used as a dash)
    text = text.replace(" - ", ' - <break time="100ms"/> ')

    # Comma followed by whitespace
    text = re.sub(r",\s+", ', <break time="150ms"/> ', text)

    # Semicolon followed by whitespace
    text = re.sub(r";\s+", '; <break time="250ms"/> ', text)

    # Colon followed by whitespace
    text = re.sub(r":\s+", ': <break time="200ms"/> ', text)

    return text


def trailing_pause_ms(original_text: str) -> int:
    """Return inter-sentence silence duration (ms) based on ending punctuation.

    Examines the *original* sentence text (before TTS cleaning) so that
    trailing emoji and raw punctuation are still visible.
    """
    s = original_text.rstrip()
    if not s:
        return 200

    # Check multi-char patterns first (longest match wins)
    if re.search(r"!{3,}$", s):
        return 400
    if s.endswith("?!") or s.endswith("!?"):
        return 350
    if s.endswith("!!"):
        return 350
    if s.endswith("...") or s.endswith("\u2026"):
        return 400
    if s.endswith("."):
        return 350
    if s.endswith("?"):
        return 350
    if s.endswith("!"):
        return 300

    # Trailing emoji
    if _EMOJI_RE.search(s[-2:]):
        return 250

    return 200


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
    ssml = False
    if spd != 100:
        escaped = xml_escape(clean)
        escaped = _insert_ssml_breaks(escaped)
        tts_text = f'<speak><prosody rate="{spd}%">{escaped}</prosody></speak>'
        ssml = True

    log.info("[TTS] request: %d chars (ssml=%s, payload=%d chars) | %s",
             len(clean), ssml, len(tts_text), clean[:120])
    log.debug("[TTS] full payload: %s", tts_text[:300])

    sem = _get_semaphore()
    async with sem:
        try:
            client = _get_client()
            t0 = time.monotonic()
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
            elapsed = time.monotonic() - t0
            if resp.status_code != 200:
                log.error("[TTS] HTTP %d after %.2fs for: %s", resp.status_code, elapsed, clean[:80])
                return b""

            pcm_data = resp.content
            duration = len(pcm_data) / 2 / TTS_SAMPLE_RATE
            log.info("[TTS] result: %d bytes (%.2fs audio) in %.2fs | %s",
                     len(pcm_data), duration, elapsed, clean[:120])

            # Warn on suspiciously short audio for non-trivial input
            if len(clean) > 10 and duration < 0.3:
                log.warning("[TTS] TRUNCATED? %d chars → %.3fs audio (expected ~%.1fs) | full: %s",
                            len(clean), duration, len(clean) / 14.0, clean)
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
