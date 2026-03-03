"""Server event factory functions (dict-based, matching OpenAI Realtime API)."""

from __future__ import annotations

from typing import Any

from .protocol import gen_event_id


# ---------------------------------------------------------------------------
# Session events
# ---------------------------------------------------------------------------
def session_created(session_obj: dict) -> dict:
    return {
        "event_id": gen_event_id(),
        "type": "session.created",
        "session": session_obj,
    }


def session_updated(session_obj: dict) -> dict:
    return {
        "event_id": gen_event_id(),
        "type": "session.updated",
        "session": session_obj,
    }


# ---------------------------------------------------------------------------
# Input audio buffer events
# ---------------------------------------------------------------------------
def input_audio_buffer_committed(item_id: str) -> dict:
    return {
        "event_id": gen_event_id(),
        "type": "input_audio_buffer.committed",
        "item_id": item_id,
    }


def input_audio_buffer_cleared() -> dict:
    return {
        "event_id": gen_event_id(),
        "type": "input_audio_buffer.cleared",
    }


def input_audio_buffer_speech_started(audio_start_ms: int) -> dict:
    return {
        "event_id": gen_event_id(),
        "type": "input_audio_buffer.speech_started",
        "audio_start_ms": audio_start_ms,
    }


def input_audio_buffer_speech_stopped(audio_end_ms: int) -> dict:
    return {
        "event_id": gen_event_id(),
        "type": "input_audio_buffer.speech_stopped",
        "audio_end_ms": audio_end_ms,
    }


# ---------------------------------------------------------------------------
# Conversation events
# ---------------------------------------------------------------------------
def conversation_item_created(item: dict) -> dict:
    return {
        "event_id": gen_event_id(),
        "type": "conversation.item.created",
        "item": item,
    }


def input_audio_transcription_completed(item_id: str, content_index: int, transcript: str) -> dict:
    return {
        "event_id": gen_event_id(),
        "type": "conversation.item.input_audio_transcription.completed",
        "item_id": item_id,
        "content_index": content_index,
        "transcript": transcript,
    }


# ---------------------------------------------------------------------------
# Response lifecycle events
# ---------------------------------------------------------------------------
def response_created(response_obj: dict) -> dict:
    return {
        "event_id": gen_event_id(),
        "type": "response.created",
        "response": response_obj,
    }


def response_done(response_obj: dict) -> dict:
    return {
        "event_id": gen_event_id(),
        "type": "response.done",
        "response": response_obj,
    }


# ---------------------------------------------------------------------------
# Response output item events
# ---------------------------------------------------------------------------
def response_output_item_added(response_id: str, output_index: int, item: dict) -> dict:
    return {
        "event_id": gen_event_id(),
        "type": "response.output_item.added",
        "response_id": response_id,
        "output_index": output_index,
        "item": item,
    }


def response_output_item_done(response_id: str, output_index: int, item: dict) -> dict:
    return {
        "event_id": gen_event_id(),
        "type": "response.output_item.done",
        "response_id": response_id,
        "output_index": output_index,
        "item": item,
    }


# ---------------------------------------------------------------------------
# Response content part events
# ---------------------------------------------------------------------------
def response_content_part_added(
    response_id: str, item_id: str, output_index: int, content_index: int, part: dict
) -> dict:
    return {
        "event_id": gen_event_id(),
        "type": "response.content_part.added",
        "response_id": response_id,
        "item_id": item_id,
        "output_index": output_index,
        "content_index": content_index,
        "part": part,
    }


def response_content_part_done(
    response_id: str, item_id: str, output_index: int, content_index: int, part: dict
) -> dict:
    return {
        "event_id": gen_event_id(),
        "type": "response.content_part.done",
        "response_id": response_id,
        "item_id": item_id,
        "output_index": output_index,
        "content_index": content_index,
        "part": part,
    }


# ---------------------------------------------------------------------------
# Response audio events
# ---------------------------------------------------------------------------
def response_audio_delta(response_id: str, item_id: str, output_index: int, content_index: int, delta: str) -> dict:
    return {
        "event_id": gen_event_id(),
        "type": "response.audio.delta",
        "response_id": response_id,
        "item_id": item_id,
        "output_index": output_index,
        "content_index": content_index,
        "delta": delta,
    }


def response_audio_done(response_id: str, item_id: str, output_index: int, content_index: int) -> dict:
    return {
        "event_id": gen_event_id(),
        "type": "response.audio.done",
        "response_id": response_id,
        "item_id": item_id,
        "output_index": output_index,
        "content_index": content_index,
    }


# ---------------------------------------------------------------------------
# Response audio transcript events
# ---------------------------------------------------------------------------
def response_audio_transcript_delta(
    response_id: str, item_id: str, output_index: int, content_index: int, delta: str
) -> dict:
    return {
        "event_id": gen_event_id(),
        "type": "response.audio_transcript.delta",
        "response_id": response_id,
        "item_id": item_id,
        "output_index": output_index,
        "content_index": content_index,
        "delta": delta,
    }


def response_audio_transcript_done(
    response_id: str, item_id: str, output_index: int, content_index: int, transcript: str
) -> dict:
    return {
        "event_id": gen_event_id(),
        "type": "response.audio_transcript.done",
        "response_id": response_id,
        "item_id": item_id,
        "output_index": output_index,
        "content_index": content_index,
        "transcript": transcript,
    }


# ---------------------------------------------------------------------------
# Error events
# ---------------------------------------------------------------------------
def error_event(message: str, error_type: str = "server_error", code: str | None = None) -> dict:
    err: dict[str, Any] = {"type": error_type, "message": message}
    if code:
        err["code"] = code
    return {
        "event_id": gen_event_id(),
        "type": "error",
        "error": err,
    }
