#!/usr/bin/env python3
"""Concurrent TTS test — fires 2 requests 0.1s apart, checks both succeed.

Usage:
    TTS_URL=http://localhost:9000 .venv/bin/python scripts/test_concurrent_tts.py
"""

from __future__ import annotations

import asyncio
import logging
import os
import sys
import time

# Allow running from repo root without installing the package
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from realtime_api.tts_client import synthesize  # noqa: E402

TTS_SAMPLE_RATE = 22050

TEXTS = [
    (
        "The history of artificial intelligence began in the mid twentieth century "
        "when researchers first proposed that machines could be made to simulate "
        "human reasoning. Early programs could prove mathematical theorems and play "
        "simple games like checkers. Over the decades, the field went through cycles "
        "of optimism and disappointment, known as AI winters. Today, deep learning "
        "and large language models have brought a new wave of excitement and practical "
        "applications across every industry, from healthcare to transportation to "
        "creative arts, changing how we live and work."
    ),
    (
        "The ocean covers more than seventy percent of our planet's surface and holds "
        "ninety seven percent of all water on Earth. Its deepest point, the Mariana "
        "Trench, plunges nearly eleven kilometres below sea level. Marine ecosystems "
        "support an incredible diversity of life, from microscopic plankton to the "
        "blue whale, the largest animal ever known to have existed. Coral reefs, "
        "sometimes called the rainforests of the sea, provide habitat for roughly "
        "a quarter of all marine species despite covering less than one percent of "
        "the ocean floor. Understanding and protecting these ecosystems is vital."
    ),
]


async def _run_one(idx: int, text: str, tts_url: str) -> dict:
    """Run a single TTS request and return metrics."""
    t0 = time.monotonic()
    pcm = await synthesize(text, tts_url=tts_url)
    elapsed = time.monotonic() - t0
    duration = len(pcm) / 2 / TTS_SAMPLE_RATE if pcm else 0.0
    return {
        "idx": idx,
        "chars": len(text),
        "bytes": len(pcm),
        "audio_sec": round(duration, 2),
        "wall_sec": round(elapsed, 2),
        "ok": len(pcm) > 0,
    }


async def main():
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)-5s %(name)s | %(message)s",
        datefmt="%H:%M:%S",
    )

    tts_url = os.environ.get("TTS_URL", "http://localhost:9000")
    print(f"\n=== Concurrent TTS test ===")
    print(f"TTS endpoint: {tts_url}")
    print(f"Requests: {len(TEXTS)}, stagger: 0.1s\n")

    async def staggered(idx: int, text: str, delay: float):
        if delay > 0:
            await asyncio.sleep(delay)
        return await _run_one(idx, text, tts_url)

    t_total = time.monotonic()
    results = await asyncio.gather(
        staggered(0, TEXTS[0], 0.0),
        staggered(1, TEXTS[1], 0.1),
    )
    wall_total = time.monotonic() - t_total

    print(f"\n{'='*60}")
    all_ok = True
    for r in results:
        status = "PASS" if r["ok"] else "FAIL"
        if not r["ok"]:
            all_ok = False
        print(
            f"  [{status}] Request {r['idx']}: "
            f"{r['chars']} chars → {r['bytes']} bytes "
            f"({r['audio_sec']}s audio) in {r['wall_sec']}s"
        )

    print(f"\n  Total wall time: {wall_total:.2f}s")
    print(f"  Result: {'ALL PASSED' if all_ok else 'SOME FAILED'}")
    print(f"{'='*60}\n")

    sys.exit(0 if all_ok else 1)


if __name__ == "__main__":
    asyncio.run(main())
