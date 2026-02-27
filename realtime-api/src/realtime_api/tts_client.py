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

# Max chars of *cleaned* text per TTS request.
# After SSML wrapping (~46 chars) + break tags (~23 chars per comma), 800 chars
# worst-case ≈ 800 + 20×23 + 46 = 1306 SSML chars — well under Magpie's 2000 limit.
_MAX_CLEAN_CHARS = 800


def _split_for_tts(text: str, max_chars: int = _MAX_CLEAN_CHARS) -> list[str]:
    """Split *text* into chunks of at most *max_chars* characters.

    Tries to break at the last ``", "`` before the limit, then last ``" "``,
    and hard-cuts only as a last resort.  Returns a single-element list when
    the text already fits.
    """
    if len(text) <= max_chars:
        return [text]

    chunks: list[str] = []
    remaining = text
    while len(remaining) > max_chars:
        window = remaining[:max_chars]
        # Prefer splitting at last ", " (natural pause)
        idx = window.rfind(", ")
        if idx > 0:
            cut = idx + 2  # keep the comma+space with the left chunk
        else:
            # Fall back to last space
            idx = window.rfind(" ")
            if idx > 0:
                cut = idx + 1
            else:
                # Hard cut — no good break point
                cut = max_chars
        chunk = remaining[:cut].strip()
        if chunk:
            chunks.append(chunk)
        remaining = remaining[cut:].strip()

    if remaining:
        chunks.append(remaining)
    return chunks


# Module-level client — reused across requests for connection pooling
_client: httpx.AsyncClient | None = None

# Concurrency gate — limits parallel TTS requests across all sessions
_tts_semaphore: asyncio.Semaphore | None = None


def _get_client() -> httpx.AsyncClient:
    global _client
    if _client is None or _client.is_closed:
        _client = httpx.AsyncClient(timeout=httpx.Timeout(120.0, read=60.0))
    return _client


def _reset_client() -> httpx.AsyncClient:
    """Close the existing client and create a fresh one (stale-connection recovery)."""
    global _client
    if _client is not None and not _client.is_closed:
        # fire-and-forget close; we create a new one immediately
        asyncio.get_event_loop().create_task(_client.aclose())
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


async def _synthesize_single(
    clean: str,
    url: str,
    voice: str,
    speed: int,
    cancel_event: asyncio.Event | None = None,
    _retry: bool = False,
) -> bytes:
    """Synthesize a single chunk of cleaned text via Magpie TTS.

    Handles SSML wrapping, HTTP POST, and logging.  Acquires the concurrency
    semaphore independently so other sessions can interleave between chunks.

    On truncated responses (stale HTTP connection), retries once with a fresh
    httpx client.

    Returns raw PCM16 bytes at 22050 Hz (empty on error).
    """
    if cancel_event and cancel_event.is_set():
        return b""

    # Wrap in SSML prosody if speed != 100; xml_escape prevents broken markup
    tts_text = clean
    ssml = False
    if speed != 100:
        escaped = xml_escape(clean)
        escaped = _insert_ssml_breaks(escaped)
        tts_text = f'<speak><prosody rate="{speed}%">{escaped}</prosody></speak>'
        ssml = True

    tag = "[TTS-RETRY]" if _retry else "[TTS]"
    log.info("%s request: %d chars (ssml=%s, payload=%d chars) | %s",
             tag, len(clean), ssml, len(tts_text), clean[:120])
    log.debug("%s full payload: %s", tag, tts_text[:300])

    sem = _get_semaphore()
    pcm_data = b""
    need_retry = False

    async with sem:
        try:
            client = _get_client()
            t0 = time.monotonic()
            resp = await client.post(
                url,
                data={
                    "text": tts_text,
                    "language": "en-US",
                    "voice": voice,
                    "encoding": "LINEAR_PCM",
                    "sample_rate_hz": str(TTS_SAMPLE_RATE),
                },
            )
            elapsed = time.monotonic() - t0
            if resp.status_code != 200:
                log.error("%s HTTP %d after %.2fs for: %s", tag, resp.status_code, elapsed, clean[:80])
                return b""

            pcm_data = resp.content
            duration = len(pcm_data) / 2 / TTS_SAMPLE_RATE
            log.info("%s result: %d bytes (%.2fs audio) in %.2fs | %s",
                     tag, len(pcm_data), duration, elapsed, clean[:120])

            # Detect truncated audio — ratio-based: expect at least 15ms per char
            # (normal speech at 125% ≈ 60-80ms/char; 15ms is very conservative)
            min_expected = max(0.5, len(clean) * 0.015)
            if len(clean) > 10 and duration < min_expected and not _retry:
                log.warning("%s TRUNCATED: %d chars → %.3fs audio (expected ≥%.2fs), "
                            "will retry with fresh connection | %s",
                            tag, len(clean), duration, min_expected, clean[:80])
                need_retry = True

            if len(clean) > 10 and duration < min_expected and _retry:
                log.warning("%s STILL TRUNCATED after retry: %d chars → %.3fs audio "
                            "(expected ≥%.2fs) | full: %s",
                            tag, len(clean), duration, min_expected, clean)

        except httpx.ConnectError:
            log.error("%s cannot connect to %s", tag, url)
            return b""
        except httpx.ReadTimeout:
            log.error("%s read timeout after %.0fs for: %s", tag,
                      time.monotonic() - t0, clean[:80])
            return b""
        except Exception as e:
            log.error("%s error (%s): %s", tag, type(e).__name__, e)
            return b""

    # Retry OUTSIDE the semaphore to avoid deadlock
    if need_retry:
        _reset_client()
        return await _synthesize_single(clean, url, voice, speed, cancel_event, _retry=True)

    return pcm_data


async def synthesize(
    text: str,
    voice: str | None = None,
    speed: int | None = None,
    tts_url: str | None = None,
    cancel_event: asyncio.Event | None = None,
) -> bytes:
    """Synthesize text via Magpie TTS, returning complete PCM16 audio at 22050Hz.

    Long text is automatically split into chunks that stay under Magpie's
    2000-char SSML limit.  For the common case (text < 800 chars after
    cleaning) this returns a single request with no overhead.

    Returns:
        Raw PCM16 bytes at 22050Hz (empty bytes if nothing to synthesize).
    """
    url = (tts_url or settings.tts_url).rstrip("/") + "/v1/audio/synthesize"
    full_voice = resolve_voice(voice or settings.default_voice)
    spd = speed if speed is not None else settings.tts_speed

    # Clean text: strip emoji, markdown, normalize whitespace
    clean = _clean_for_tts(text)
    if not clean:
        log.debug("[TTS] skipping empty text after cleanup (original: %s)", text[:40])
        return b""

    # Split into chunks that fit Magpie's payload limit
    chunks = _split_for_tts(clean)
    if len(chunks) > 1:
        log.warning("[TTS] text too long (%d chars), split into %d chunks",
                    len(clean), len(chunks))

    pcm_parts: list[bytes] = []
    for chunk in chunks:
        pcm = await _synthesize_single(chunk, url, full_voice, spd, cancel_event)
        if pcm:
            pcm_parts.append(pcm)
    return b"".join(pcm_parts)


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
