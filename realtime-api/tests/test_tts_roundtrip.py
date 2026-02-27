#!/usr/bin/env python3
"""TTS → STT round-trip test.

Exercises the same TTS + STT pipeline the server uses, running against
the exposed host ports (localhost:9000 for TTS, localhost:9002 for STT).

Usage:
    TTS_URL=http://localhost:9000 STT_URL=http://localhost:9002 python3 tests/test_tts_roundtrip.py
"""

from __future__ import annotations

import asyncio
import io
import os
import struct
import sys
import wave

# Allow running from the repo root
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from realtime_api.audio import resample_pcm16
from realtime_api.stt_client import transcribe
from realtime_api.tts_client import synthesize

TTS_URL = os.environ.get("TTS_URL", "http://localhost:9000")
STT_URL = os.environ.get("STT_URL", "http://localhost:9002")

TTS_SAMPLE_RATE = 22050
CLIENT_SAMPLE_RATE = 24000

TEST_TEXT = (
    "The sky is blue and the grass is green. "
    "Birds are singing in the morning light. "
    "A gentle breeze carries the scent of flowers."
)

TEST_SENTENCES = [
    "The sky is blue and the grass is green.",
    "Birds are singing in the morning light.",
    "A gentle breeze carries the scent of flowers.",
]


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

    print(f"  Input: {TEST_TEXT}")
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

    # Check key words are present
    lower = stt_text.lower()
    assert "sky" in lower, f"Expected 'sky' in STT output: {stt_text}"
    assert "blue" in lower, f"Expected 'blue' in STT output: {stt_text}"
    print("  PASS: key words found in STT output")

    return resampled, stt_text


async def test_sentence_mode():
    """Synthesize each sentence individually, concatenate, STT round-trip."""
    print("\n=== Test: Sentence-by-sentence mode ===")

    all_pcm = b""
    for i, sentence in enumerate(TEST_SENTENCES):
        print(f"  Sentence {i+1}: {sentence}")
        tts_pcm = await synthesize(sentence, tts_url=TTS_URL)
        assert tts_pcm, f"TTS returned empty audio for sentence {i+1}"

        dur = pcm_duration(tts_pcm, TTS_SAMPLE_RATE)
        print(f"    TTS: {len(tts_pcm)} bytes ({dur:.2f}s)")

        resampled = resample_pcm16(tts_pcm, TTS_SAMPLE_RATE, CLIENT_SAMPLE_RATE)
        all_pcm += resampled

    dur_total = pcm_duration(all_pcm, CLIENT_SAMPLE_RATE)
    print(f"  Total concatenated: {len(all_pcm)} bytes ({dur_total:.2f}s @ {CLIENT_SAMPLE_RATE}Hz)")

    write_wav("tests/sentence_mode.wav", all_pcm, CLIENT_SAMPLE_RATE)

    stt_text = await transcribe(all_pcm, stt_url=STT_URL)
    print(f"  STT output: {stt_text}")

    lower = stt_text.lower()
    assert "sky" in lower, f"Expected 'sky' in STT output: {stt_text}"
    assert "blue" in lower, f"Expected 'blue' in STT output: {stt_text}"
    print("  PASS: key words found in STT output")

    return all_pcm, stt_text


async def main():
    print(f"TTS_URL: {TTS_URL}")
    print(f"STT_URL: {STT_URL}")

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
    assert diff < 2.0, f"Duration difference too large: {diff:.2f}s (expected < 2.0s)"
    print("  PASS: durations within 2s of each other")

    print(f"\n  Whole STT:    {stt_whole}")
    print(f"  Sentence STT: {stt_sentences}")

    print("\n=== ALL TESTS PASSED ===")


if __name__ == "__main__":
    asyncio.run(main())
