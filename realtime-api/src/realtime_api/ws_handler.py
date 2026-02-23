"""WebSocket /v1/realtime endpoint + event dispatch."""

from __future__ import annotations

import asyncio
import logging

from starlette.websockets import WebSocket, WebSocketDisconnect

from . import events
from .audio import decode_audio_appendix, tts_pcm16_to_client_base64
from .barge_in import BargeInEvaluator
from .llm_client import stream_sentences
from .protocol import gen_content_part_id, gen_item_id, gen_response_id
from .session import Session
from .stt_client import transcribe
from .tts_client import synthesize_stream

log = logging.getLogger(__name__)


async def handle_realtime_ws(ws: WebSocket, model: str | None = None):
    """Main handler for a single Realtime API WebSocket connection."""
    await ws.accept(subprotocol="realtime")

    session = Session()
    session.init_vad()
    log.info("Session %s created", session.id)

    # Send session.created
    await ws.send_json(events.session_created(session.to_dict()))

    # Start sender task
    sender_task = asyncio.create_task(_sender_loop(ws, session))

    try:
        await _receiver_loop(ws, session)
    except WebSocketDisconnect:
        log.info("Session %s disconnected", session.id)
    except Exception as e:
        log.error("Session %s error: %s", session.id, e)
    finally:
        session.cancel_event.set()
        sender_task.cancel()
        if session._response_task and not session._response_task.done():
            session._response_task.cancel()
        log.info("Session %s closed", session.id)


async def _sender_loop(ws: WebSocket, session: Session):
    """Drain the session send queue and forward events to the WebSocket."""
    try:
        while True:
            event = await session.send_queue.get()
            try:
                await ws.send_json(event)
            except Exception:
                break
    except asyncio.CancelledError:
        pass


async def _receiver_loop(ws: WebSocket, session: Session):
    """Receive client events and dispatch."""
    while True:
        data = await ws.receive_json()
        event_type = data.get("type", "")

        try:
            if event_type == "session.update":
                await _handle_session_update(session, data)
            elif event_type == "input_audio_buffer.append":
                await _handle_audio_append(session, data)
            elif event_type == "input_audio_buffer.commit":
                await _handle_audio_commit(session)
            elif event_type == "input_audio_buffer.clear":
                await _handle_audio_clear(session)
            elif event_type == "response.create":
                await _handle_response_create(session, data)
            elif event_type == "response.cancel":
                await _handle_response_cancel(session)
            else:
                await session.send(
                    events.error_event(f"Unknown event type: {event_type}", code="unknown_event")
                )
        except Exception as e:
            log.error("Error handling %s: %s", event_type, e, exc_info=True)
            await session.send(events.error_event(str(e)))


# ---------------------------------------------------------------------------
# Event handlers
# ---------------------------------------------------------------------------
async def _handle_session_update(session: Session, data: dict):
    session_data = data.get("session", {})
    session.config.update_from_dict(session_data)
    session.init_vad()
    await session.send(events.session_updated(session.to_dict()))
    log.info("Session %s updated", session.id)


async def _handle_audio_append(session: Session, data: dict):
    audio_b64 = data.get("audio", "")
    if not audio_b64:
        return

    # Append to buffer
    session.audio_buffer.append(audio_b64)

    # Feed to VAD if enabled
    vad = session.vad
    if vad is None:
        return

    pcm_bytes = decode_audio_appendix(audio_b64)

    # Update VAD speaking state
    vad.is_speaking = session.is_speaking

    vad_events = vad.process_chunk(pcm_bytes)
    for vad_event in vad_events:
        from .vad import VADEventType

        if vad_event.type == VADEventType.SPEECH_STARTED:
            await session.send(events.input_audio_buffer_speech_started(vad_event.audio_ms))

            # If assistant is speaking and AEC mode, start barge-in evaluation
            if session.is_speaking and _is_aec_mode(session):
                _start_barge_in_evaluation(session, vad_event.audio_bytes)

        elif vad_event.type == VADEventType.SPEECH_STOPPED:
            await session.send(events.input_audio_buffer_speech_stopped(vad_event.audio_ms))

            if session.is_speaking and _is_aec_mode(session):
                # Barge-in: evaluate the accumulated audio
                asyncio.create_task(
                    _evaluate_barge_in(session, vad_event.audio_bytes)
                )
            else:
                # Normal turn end — auto-commit with the VAD-captured audio
                await _auto_commit(session, vad_event.audio_bytes)


def _is_aec_mode(session: Session) -> bool:
    td = session.config.turn_detection
    return td is not None and td.aec_mode == "aec"


def _start_barge_in_evaluation(session: Session, initial_audio: bytes):
    """Initialize barge-in audio collection (the VAD already accumulated speech)."""
    # The VAD speech_started event already includes pre-roll audio,
    # but the main evaluation happens on speech_stopped with all accumulated audio
    log.info("Barge-in: speech detected during response playback, waiting for turn end...")


async def _evaluate_barge_in(session: Session, audio_bytes: bytes):
    """Run intelligent barge-in evaluation on accumulated speech audio."""
    evaluator = BargeInEvaluator()
    decision = await evaluator.evaluate(
        audio_pcm16_24khz=audio_bytes,
        assistant_last_text=session.current_response_text,
    )

    if decision == "STOP":
        log.info("Barge-in: STOP — cancelling response and starting new turn")
        await _handle_response_cancel(session)
        # Start new turn with the captured audio
        await _run_pipeline(session, audio_bytes)
    else:
        log.info("Barge-in: CONTINUE — resuming playback")
        # Discard the snippet, keep playing


async def _handle_audio_commit(session: Session):
    if session.audio_buffer.is_empty:
        return

    pcm_data = session.audio_buffer.commit()
    item_id = gen_item_id()
    await session.send(events.input_audio_buffer_committed(item_id))

    # Run the STT → LLM → TTS pipeline
    asyncio.create_task(_run_pipeline(session, pcm_data, item_id=item_id))


async def _auto_commit(session: Session, vad_audio: bytes):
    """Auto-commit from VAD speech_stopped with the VAD-accumulated audio."""
    item_id = gen_item_id()
    await session.send(events.input_audio_buffer_committed(item_id))
    session.audio_buffer.clear()  # Clear the main buffer since we use VAD audio

    asyncio.create_task(_run_pipeline(session, vad_audio, item_id=item_id))


async def _handle_audio_clear(session: Session):
    session.audio_buffer.clear()
    if session.vad:
        session.vad.reset()
    await session.send(events.input_audio_buffer_cleared())


async def _handle_response_create(session: Session, data: dict):
    """Handle explicit response.create — may include text input for text-based generation."""
    resp_data = data.get("response", {})
    input_items = resp_data.get("input", [])

    # If input items provided, add them to conversation
    for item in input_items:
        if item.get("type") == "message" and item.get("role") == "user":
            for content in item.get("content", []):
                if content.get("type") == "input_text":
                    session.conversation.add_user_message(content["text"])

    # Run LLM → TTS pipeline without STT
    asyncio.create_task(_run_response_pipeline(session))


async def _handle_response_cancel(session: Session):
    session.cancel_event.set()
    if session._response_task and not session._response_task.done():
        session._response_task.cancel()
    session.is_speaking = False


# ---------------------------------------------------------------------------
# Pipeline: STT → LLM → TTS
# ---------------------------------------------------------------------------
async def _run_pipeline(session: Session, pcm_data: bytes, item_id: str | None = None):
    """Full pipeline: transcribe audio, run LLM, stream TTS back."""
    # Cancel any existing response
    if session._response_task and not session._response_task.done():
        session.cancel_event.set()
        session._response_task.cancel()
        try:
            await session._response_task
        except (asyncio.CancelledError, Exception):
            pass

    session.cancel_event.clear()
    item_id = item_id or gen_item_id()

    async def _pipeline():
        # 1. STT: transcribe
        transcript = await transcribe(pcm_data)
        if not transcript:
            log.warning("Empty transcription, skipping response")
            return

        # Emit transcription event
        await session.send(
            events.input_audio_transcription_completed(item_id, 0, transcript)
        )

        # Add user message to conversation
        session.conversation.add_user_message(transcript, item_id=item_id)
        log.info("User: %s", transcript)

        # 2. LLM → TTS
        await _generate_response(session)

    session._response_task = asyncio.create_task(_pipeline())


async def _run_response_pipeline(session: Session):
    """Pipeline without STT — for text-based or re-generate requests."""
    if session._response_task and not session._response_task.done():
        session.cancel_event.set()
        session._response_task.cancel()
        try:
            await session._response_task
        except (asyncio.CancelledError, Exception):
            pass

    session.cancel_event.clear()
    session._response_task = asyncio.create_task(_generate_response(session))


async def _generate_response(session: Session):
    """Run LLM streaming → sentence splitting → TTS streaming → audio events."""
    response_id = gen_response_id()
    output_item_id = gen_item_id()
    audio_content_id = gen_content_part_id()
    transcript_content_id = gen_content_part_id()

    # Response created
    response_obj = {
        "id": response_id,
        "object": "realtime.response",
        "status": "in_progress",
        "output": [],
    }
    await session.send(events.response_created(response_obj))

    # Output item
    output_item = {
        "id": output_item_id,
        "object": "realtime.item",
        "type": "message",
        "role": "assistant",
        "content": [],
    }
    await session.send(events.response_output_item_added(response_id, 0, output_item))

    # Content parts — audio and transcript
    has_audio = "audio" in session.config.modalities
    if has_audio:
        await session.send(
            events.response_content_part_added(
                response_id, output_item_id, 0, 0,
                {"type": "audio", "audio": ""},
            )
        )
        await session.send(
            events.response_content_part_added(
                response_id, output_item_id, 0, 1,
                {"type": "audio_transcript", "transcript": ""},
            )
        )

    session.is_speaking = True
    session.current_response_text = ""
    full_transcript = ""
    cancelled = False

    try:
        messages = session.conversation.to_chat_messages(session.config.instructions)

        # Stream LLM → sentences → TTS
        async for sentence in stream_sentences(
            messages,
            temperature=session.config.temperature,
            cancel_event=session.cancel_event,
        ):
            if session.cancel_event.is_set():
                cancelled = True
                break

            full_transcript += sentence + " "
            session.current_response_text = full_transcript

            # Emit transcript delta
            if has_audio:
                await session.send(
                    events.response_audio_transcript_delta(
                        response_id, output_item_id, 0, 1, sentence + " ",
                    )
                )

            # Stream TTS for this sentence
            if has_audio:
                async for tts_chunk in synthesize_stream(
                    sentence,
                    voice=session.config.voice,
                    cancel_event=session.cancel_event,
                ):
                    if session.cancel_event.is_set():
                        cancelled = True
                        break
                    audio_b64 = tts_pcm16_to_client_base64(tts_chunk)
                    await session.send(
                        events.response_audio_delta(
                            response_id, output_item_id, 0, 0, audio_b64,
                        )
                    )

                if cancelled:
                    break

    except asyncio.CancelledError:
        cancelled = True
    except Exception as e:
        log.error("Response generation error: %s", e, exc_info=True)
        await session.send(events.error_event(str(e)))
        cancelled = True

    # Finalize
    session.is_speaking = False
    full_transcript = full_transcript.strip()

    if full_transcript:
        session.conversation.add_assistant_message(full_transcript, item_id=output_item_id)

    # Emit done events
    if has_audio and not cancelled:
        await session.send(
            events.response_audio_done(response_id, output_item_id, 0, 0)
        )
        await session.send(
            events.response_audio_transcript_done(
                response_id, output_item_id, 0, 1, full_transcript,
            )
        )

    # Content part done
    if has_audio:
        await session.send(
            events.response_content_part_done(
                response_id, output_item_id, 0, 0,
                {"type": "audio", "audio": ""},
            )
        )
        await session.send(
            events.response_content_part_done(
                response_id, output_item_id, 0, 1,
                {"type": "audio_transcript", "transcript": full_transcript},
            )
        )

    # Output item done
    output_item["content"] = [
        {"type": "audio", "audio": ""},
        {"type": "audio_transcript", "transcript": full_transcript},
    ]
    await session.send(
        events.response_output_item_done(response_id, 0, output_item)
    )

    # Response done
    status = "cancelled" if cancelled else "completed"
    response_obj["status"] = status
    response_obj["output"] = [output_item]
    await session.send(events.response_done(response_obj))

    log.info("Response %s %s (%d chars)", response_id, status, len(full_transcript))

    # Reset VAD after response is done (for non-AEC echo cooldown)
    if session.vad and not _is_aec_mode(session):
        session.vad.reset()
