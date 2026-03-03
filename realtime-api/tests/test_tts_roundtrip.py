#!/usr/bin/env python3
"""TTS -> STT round-trip test.

Exercises the same TTS + STT pipeline the server uses, running against
the exposed host ports (localhost:9000 for TTS, localhost:9002 for STT).

Tests both whole-response and sentence-by-sentence modes, using the same
``_split_buffer`` sentence splitter the real server pipeline uses.

Usage:
    TTS_URL=http://localhost:9000 STT_URL=http://localhost:9002 python3 tests/test_tts_roundtrip.py
"""

from __future__ import annotations

import asyncio
import os
import sys
import wave

# Allow running from the repo root
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from realtime_api.audio import resample_pcm16
from realtime_api.llm_client import _split_buffer
from realtime_api.stt_client import transcribe
from realtime_api.tts_client import synthesize, _split_for_tts, _MAX_CLEAN_CHARS

TTS_URL = os.environ.get("TTS_URL", "http://localhost:9000")
STT_URL = os.environ.get("STT_URL", "http://localhost:9002")

TTS_SAMPLE_RATE = 22050
CLIENT_SAMPLE_RATE = 24000

TEST_TEXT = (
    "Here is an exceptionally long, densely packed sentence\u2014crafted to maximize "
    "syntactic complexity, semantic density, and conceptual recursion while remaining "
    "grammatically precise and purposeful: Though the ostensibly coherent, methodically "
    "structured, and meticulously detailed exposition\u2014comprising interdependent clauses "
    "that recursively amplify thematic resonance, epistemological uncertainty, and semiotic "
    "ambiguity through layered allusions to ontological instability, causal paradoxes, and "
    "the epistemological fragility of human perception\u2014inevitably culminates in a "
    "resolution that is simultaneously thematically unavoidable, philosophically unsettling, "
    "and linguistically self-referential, thereby exposing the inherent tension between "
    "narrative closure and the irreducible complexity of meaning itself."
)


def write_wav(filename: str, pcm_bytes: bytes, sample_rate: int):
    """Write raw PCM16 bytes to a WAV file for debugging."""
    with wave.open(filename, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sample_rate)
        wf.writeframes(pcm_bytes)
    print(f"  Saved {filename} ({len(pcm_bytes)} bytes, {len(pcm_bytes)/2/sample_rate:.2f}s)")


def pcm_duration(pcm_bytes: bytes, sample_rate: int) -> float:
    return len(pcm_bytes) / 2 / sample_rate


async def test_whole_mode():
    """Synthesize full text as one call, resample, STT round-trip."""
    print("\n=== Test: Whole-response mode ===")

    print(f"  Input: {TEST_TEXT[:80]}...")
    tts_pcm = await synthesize(TEST_TEXT, tts_url=TTS_URL)
    assert tts_pcm, "TTS returned empty audio"

    dur = pcm_duration(tts_pcm, TTS_SAMPLE_RATE)
    print(f"  TTS output: {len(tts_pcm)} bytes ({dur:.2f}s @ {TTS_SAMPLE_RATE}Hz)")

    resampled = resample_pcm16(tts_pcm, TTS_SAMPLE_RATE, CLIENT_SAMPLE_RATE)
    dur_r = pcm_duration(resampled, CLIENT_SAMPLE_RATE)
    print(f"  Resampled:  {len(resampled)} bytes ({dur_r:.2f}s @ {CLIENT_SAMPLE_RATE}Hz)")

    write_wav("tests/whole_mode.wav", resampled, CLIENT_SAMPLE_RATE)

    stt_text = await transcribe(resampled, stt_url=STT_URL)
    print(f"  STT output: {stt_text}")

    lower = stt_text.lower()
    for keyword in ("complexity", "sentence", "grammatically"):
        if keyword in lower:
            print(f"  PASS: found '{keyword}' in STT output")
            break
    else:
        assert False, f"Expected at least one key word in STT output: {stt_text}"

    return resampled, stt_text


async def test_sentence_mode():
    """Split text via _split_buffer, synthesize each sentence, concatenate, STT round-trip."""
    print("\n=== Test: Sentence-by-sentence mode ===")

    # Use the same sentence splitter as the real server pipeline
    sentences, remainder = _split_buffer(TEST_TEXT)
    if remainder.strip():
        sentences.append(remainder.strip())

    print(f"  Split into {len(sentences)} sentence(s):")
    for i, s in enumerate(sentences):
        print(f"    [{i+1}] {s[:70]}{'...' if len(s) > 70 else ''}")

    all_pcm = b""
    for i, sentence in enumerate(sentences):
        tts_pcm = await synthesize(sentence, tts_url=TTS_URL)
        assert tts_pcm, f"TTS returned empty audio for sentence {i+1}: {sentence[:50]}..."

        dur = pcm_duration(tts_pcm, TTS_SAMPLE_RATE)
        print(f"  Sentence {i+1}: {len(tts_pcm)} bytes ({dur:.2f}s)")

        resampled = resample_pcm16(tts_pcm, TTS_SAMPLE_RATE, CLIENT_SAMPLE_RATE)
        all_pcm += resampled

    dur_total = pcm_duration(all_pcm, CLIENT_SAMPLE_RATE)
    print(f"  Total concatenated: {len(all_pcm)} bytes ({dur_total:.2f}s @ {CLIENT_SAMPLE_RATE}Hz)")

    write_wav("tests/sentence_mode.wav", all_pcm, CLIENT_SAMPLE_RATE)

    stt_text = await transcribe(all_pcm, stt_url=STT_URL)
    print(f"  STT output: {stt_text}")

    lower = stt_text.lower()
    for keyword in ("complexity", "sentence", "grammatically"):
        if keyword in lower:
            print(f"  PASS: found '{keyword}' in STT output")
            break
    else:
        assert False, f"Expected at least one key word in STT output: {stt_text}"

    return all_pcm, stt_text


def test_dash_splitting():
    """Pure-logic test: em-dash-heavy text > 200 chars is split in loose mode."""
    print("\n=== Test: Dash splitting (pure logic, no network) ===")

    # Build a long string joined by em-dashes — no .!? boundaries
    segments = [
        "The system processes incoming data streams efficiently",
        "transforms them through multiple neural network layers",
        "applies attention mechanisms across all token positions",
        "and finally produces coherent output sequences",
        "which are then validated against quality thresholds",
    ]
    text = " \u2014 ".join(segments)
    assert len(text) > 200, f"Test text too short: {len(text)} chars"

    parts, remainder = _split_buffer(text, loose=True)
    all_parts = parts + ([remainder] if remainder.strip() else [])

    print(f"  Input length: {len(text)} chars")
    print(f"  Split into {len(all_parts)} part(s):")
    for i, p in enumerate(all_parts):
        print(f"    [{i+1}] ({len(p)} chars) {p[:70]}{'...' if len(p) > 70 else ''}")

    assert len(all_parts) >= 2, (
        f"Expected >= 2 parts from dash splitting, got {len(all_parts)}"
    )
    for p in all_parts:
        assert len(p) <= _MAX_CLEAN_CHARS, (
            f"Part exceeds {_MAX_CLEAN_CHARS} chars: {len(p)}"
        )
    print("  PASS: dash splitting works correctly")


def test_tts_chunking():
    """Pure-logic test: 1200-char comma-heavy text is chunked by _split_for_tts."""
    print("\n=== Test: TTS chunking (pure logic, no network) ===")

    # Build a ~1200-char string with only commas — no sentence-ending punct
    phrases = [
        "the rapid advancement of neural architectures",
        "combined with ever growing datasets",
        "has led to remarkable improvements in language understanding",
        "enabling models to generate coherent text",
        "translate between languages with high fidelity",
        "summarize lengthy documents accurately",
        "answer complex questions from context",
        "write creative fiction and poetry",
        "assist with programming tasks",
        "analyze sentiment in social media posts",
        "extract structured information from unstructured text",
        "perform logical reasoning across multiple steps",
        "handle ambiguous queries with contextual awareness",
        "adapt to user preferences through interaction",
        "maintain consistent persona across conversations",
        "support multiple languages and dialects",
        "process multimodal inputs including images",
        "generate detailed explanations of complex topics",
        "produce human quality translations in real time",
        "and continue to push the boundaries of what is possible",
    ]
    text = ", ".join(phrases)
    assert len(text) > 1000, f"Test text too short: {len(text)} chars"

    chunks = _split_for_tts(text)
    print(f"  Input length: {len(text)} chars")
    print(f"  Split into {len(chunks)} chunk(s):")
    for i, c in enumerate(chunks):
        print(f"    [{i+1}] ({len(c)} chars) {c[:70]}{'...' if len(c) > 70 else ''}")

    assert len(chunks) >= 2, (
        f"Expected >= 2 chunks for {len(text)}-char input, got {len(chunks)}"
    )
    for c in chunks:
        assert len(c) <= _MAX_CLEAN_CHARS, (
            f"Chunk exceeds {_MAX_CLEAN_CHARS} chars: {len(c)}"
        )
    # All text should be preserved (no data loss)
    rejoined = ", ".join(c.strip(",").strip() for c in chunks)
    # Just verify total char count is close (splitting may consume/add minor whitespace)
    assert abs(len(rejoined) - len(text)) < len(chunks) * 5, "Chunks lost too much text"
    print("  PASS: TTS chunking works correctly")


async def main():
    print(f"TTS_URL: {TTS_URL}")
    print(f"STT_URL: {STT_URL}")

    # Pure-logic tests first (no network required)
    test_dash_splitting()
    test_tts_chunking()

    # Integration tests (require TTS + STT services)
    whole_pcm, stt_whole = await test_whole_mode()
    sentence_pcm, stt_sentences = await test_sentence_mode()

    # Compare durations
    whole_dur = pcm_duration(whole_pcm, CLIENT_SAMPLE_RATE)
    sentence_dur = pcm_duration(sentence_pcm, CLIENT_SAMPLE_RATE)
    diff = abs(whole_dur - sentence_dur)
    print(f"\n=== Comparison ===")
    print(f"  Whole duration:    {whole_dur:.2f}s")
    print(f"  Sentence duration: {sentence_dur:.2f}s")
    print(f"  Difference:        {diff:.2f}s")
    # Sentence mode may add pauses between sentences; allow more tolerance
    assert diff < 5.0, f"Duration difference too large: {diff:.2f}s (expected < 5.0s)"
    print("  PASS: durations within tolerance")

    print(f"\n  Whole STT:    {stt_whole}")
    print(f"  Sentence STT: {stt_sentences}")

    print("\n=== ALL TESTS PASSED ===")


if __name__ == "__main__":
    asyncio.run(main())
