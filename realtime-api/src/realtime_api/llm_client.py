"""Async OpenAI-compatible chat completions streaming client."""

from __future__ import annotations

import json
import logging
import re
from collections.abc import AsyncIterator

import httpx

from .config import settings

log = logging.getLogger(__name__)

# Sentence boundary: .!? + whitespace + uppercase letter (proper new sentence).
# Avoids splitting before emoji, lowercase continuations, or parenthetical asides
# like "speaking!) or …".
_SENTENCE_RE = re.compile(r"(?<=[.!?])\s+(?=[A-Z])")

# Fallback: any .!? + whitespace — used when the buffer grows too long without
# a strict-match split, so we don't starve TTS of input.
_SENTENCE_RE_LOOSE = re.compile(r"(?<=[.!?])\s+")

# If the buffer exceeds this length without a strict split, switch to _LOOSE.
_MAX_BUFFER_BEFORE_LOOSE = 200


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

    Splits on .!? followed by whitespace **and** an uppercase letter, so emoji
    continuations (``Hey! 😄 What's up?``) and parenthetical asides
    (``speaking!) or …``) stay in one chunk.  Falls back to a looser split
    when the buffer exceeds _MAX_BUFFER_BEFORE_LOOSE characters.
    """
    buffer = ""
    async for delta in stream_chat_completion(messages, model=model, temperature=temperature):
        if cancel_event and cancel_event.is_set():
            break
        buffer += delta

        # Strict regex keeps emoji/parenthetical continuations together;
        # fall back to loose split when the buffer gets very long.
        regex = (
            _SENTENCE_RE_LOOSE
            if len(buffer) > _MAX_BUFFER_BEFORE_LOOSE
            else _SENTENCE_RE
        )
        parts = regex.split(buffer)
        for sentence in parts[:-1]:
            sentence = sentence.strip()
            if sentence:
                yield sentence
        buffer = parts[-1]

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
