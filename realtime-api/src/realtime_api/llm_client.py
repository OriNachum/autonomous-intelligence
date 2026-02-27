"""Async OpenAI-compatible chat completions streaming client."""

from __future__ import annotations

import json
import logging
import re
from collections.abc import AsyncIterator

import httpx

from .config import settings

log = logging.getLogger(__name__)

# Fallback regex: any .!? + whitespace — used when the buffer grows very long
# without a proper sentence break so we don't starve TTS of input.
_SENTENCE_RE_LOOSE = re.compile(r"(?<=[.!?])\s+")

# Switch to the loose regex when the buffer exceeds this many characters.
_MAX_BUFFER_BEFORE_LOOSE = 200


# ---------------------------------------------------------------------------
# Quote / parenthesis-aware sentence splitter
# ---------------------------------------------------------------------------

_MARKDOWN_CHARS = frozenset("*_~`#")


def _find_sentence_breaks(text: str) -> list[int]:
    """Return character indices where new sentences start.

    A break is placed after terminal punctuation (``.!?``) — or a closing
    quote / paren that immediately follows terminal punctuation — when:

    1. We are not inside quotation marks or parentheses, **and**
    2. the next non-whitespace character (ignoring markdown formatting like
       ``**``) is an uppercase letter.

    This avoids splitting inside quoted speech (``"Hey! What's up?"``) and
    parenthetical asides (``(well, speaking!) or …``), while still detecting
    boundaries through markdown (``chests!** I'm`` or ``thought!\\n**Did``).
    """
    breaks: list[int] = []
    paren_depth = 0
    quote_open = False

    for i, ch in enumerate(text):
        # --- track nesting depth ---
        if ch == "\u201c":            # left "
            quote_open = True
        elif ch == "\u201d":          # right "
            quote_open = False
        elif ch == '"':               # ASCII — toggle
            quote_open = not quote_open

        if ch == "(":
            paren_depth += 1
        elif ch == ")":
            paren_depth = max(0, paren_depth - 1)

        # While nested inside quotes or parens, no boundary is possible.
        if paren_depth > 0 or quote_open:
            continue

        # --- detect sentence-ending position ---
        is_terminal = ch in ".!?"

        # A closing quote/paren right after terminal punct also ends the
        # sentence:  ."  !)  ?")  etc.
        if not is_terminal and ch in '"\u201d)':
            k = i - 1
            while k >= 0 and text[k] in '"\u201d)\u2019\'':
                k -= 1
            is_terminal = k >= 0 and text[k] in ".!?"

        if not is_terminal:
            continue

        # --- look ahead: closing-markdown*, whitespace+, opening-markdown*, uppercase ---
        j = i + 1
        # Skip closing markdown after terminal punct  (e.g. !** or ."*)
        while j < len(text) and text[j] in _MARKDOWN_CHARS:
            j += 1
        # Must find at least one whitespace character
        ws_start = j
        while j < len(text) and text[j] in " \t\n\r":
            j += 1
        if j == ws_start:
            continue
        # Start of the next sentence in raw text (may include opening markdown)
        sentence_start = j
        # Peek past opening markdown to find the actual first letter
        while j < len(text) and text[j] in _MARKDOWN_CHARS:
            j += 1
        if j < len(text) and text[j].isupper():
            breaks.append(sentence_start)

    return breaks


def _split_buffer(text: str, loose: bool = False) -> tuple[list[str], str]:
    """Split *text* into ``(complete_sentences, remaining_buffer)``.

    In normal mode uses the quote/paren-aware boundary finder.
    In *loose* mode falls back to a simple regex that ignores nesting and
    letter-case — this keeps TTS fed when the buffer grows very long without
    a proper break.
    """
    if loose:
        parts = _SENTENCE_RE_LOOSE.split(text)
        sentences = [s.strip() for s in parts[:-1] if s.strip()]
        return sentences, parts[-1]

    breaks = _find_sentence_breaks(text)
    if not breaks:
        return [], text

    sentences: list[str] = []
    start = 0
    for brk in breaks:
        sentence = text[start:brk].strip()
        if sentence:
            sentences.append(sentence)
        start = brk
    return sentences, text[start:]


async def stream_chat_completion(
    messages: list[dict],
    model: str | None = None,
    temperature: float = 0.8,
    max_tokens: int | None = None,
    base_url: str | None = None,
    api_key: str | None = None,
) -> AsyncIterator[str]:
    """Stream a chat completion, yielding text deltas.

    Uses standard OpenAI SSE streaming format.
    """
    url = (base_url or settings.openai_base_url).rstrip("/") + "/v1/chat/completions"
    key = api_key or settings.openai_api_key

    payload: dict = {
        "model": model or settings.openai_model,
        "messages": messages,
        "stream": True,
        "temperature": temperature,
        "chat_template_kwargs": {"enable_thinking": False},
    }
    if max_tokens is not None:
        payload["max_tokens"] = max_tokens

    headers = {}
    if key and key != "EMPTY":
        headers["Authorization"] = f"Bearer {key}"

    try:
        async with httpx.AsyncClient(timeout=120.0) as client:
            async with client.stream(
                "POST", url, json=payload, headers=headers
            ) as resp:
                if resp.status_code != 200:
                    body = await resp.aread()
                    log.error("LLM error %d: %s", resp.status_code, body.decode(errors="replace")[:500])
                    return

                async for line in resp.aiter_lines():
                    if not line.startswith("data: "):
                        continue
                    data = line[6:]
                    if data == "[DONE]":
                        break
                    try:
                        chunk = json.loads(data)
                        delta = chunk["choices"][0].get("delta", {})
                        content = delta.get("content")
                        if content:
                            yield content
                    except (json.JSONDecodeError, KeyError, IndexError):
                        continue

    except httpx.ConnectError:
        log.error("Cannot connect to LLM at %s", base_url or settings.openai_base_url)
    except Exception as e:
        log.error("LLM streaming error: %s", e)


async def stream_sentences(
    messages: list[dict],
    model: str | None = None,
    temperature: float = 0.8,
    cancel_event=None,
) -> AsyncIterator[str]:
    """Stream chat completion and yield complete sentences.

    Uses a quote/paren-aware splitter so punctuation inside quoted speech
    or parenthetical asides does not trigger a break.  Falls back to a
    loose regex when the buffer exceeds *_MAX_BUFFER_BEFORE_LOOSE* chars.
    """
    buffer = ""
    async for delta in stream_chat_completion(messages, model=model, temperature=temperature):
        if cancel_event and cancel_event.is_set():
            break
        buffer += delta

        sentences, buffer = _split_buffer(
            buffer, loose=len(buffer) > _MAX_BUFFER_BEFORE_LOOSE
        )
        for sentence in sentences:
            yield sentence

    # Flush remaining buffer
    if buffer.strip():
        yield buffer.strip()


async def quick_decision(
    system_prompt: str,
    user_content: str,
    model: str | None = None,
) -> str:
    """Make a quick 1-token LLM decision (for barge-in evaluation).

    Returns the first token of the response.
    """
    url = (settings.openai_base_url).rstrip("/") + "/v1/chat/completions"
    key = settings.openai_api_key
    mdl = model or settings.barge_in_model or settings.openai_model

    payload = {
        "model": mdl,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_content},
        ],
        "max_tokens": 1,
        "temperature": 0,
        "stream": False,
        "chat_template_kwargs": {"enable_thinking": False},
    }

    headers = {}
    if key and key != "EMPTY":
        headers["Authorization"] = f"Bearer {key}"

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.post(url, json=payload, headers=headers)
            if resp.status_code != 200:
                log.error("Quick decision LLM error %d", resp.status_code)
                return "STOP"  # Default to interrupting on error
            result = resp.json()
            content = result["choices"][0]["message"]["content"].strip().upper()
            return content
    except Exception as e:
        log.error("Quick decision error: %s", e)
        return "STOP"
