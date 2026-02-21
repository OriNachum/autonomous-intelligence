#!/usr/bin/env python3
"""Record voice samples from microphone for TTS training.

Usage:
    uv run scripts/record_voice.py --output data/ --speaker ori

Records N utterances with text prompts displayed on screen.
Saves WAVs + a train.jsonl for the training pipeline.
"""

import argparse
import json
import subprocess
import sys
from pathlib import Path

# Default sentences to read (short, clear, diverse phonemes)
DEFAULT_PROMPTS = [
    "The quick brown fox jumps over the lazy dog.",
    "She sells seashells by the seashore.",
    "How much wood would a woodchuck chuck if a woodchuck could chuck wood?",
    "Peter Piper picked a peck of pickled peppers.",
    "The rain in Spain stays mainly in the plain.",
    "A journey of a thousand miles begins with a single step.",
    "To be or not to be, that is the question.",
    "All that glitters is not gold.",
    "Knowledge is power, but enthusiasm pulls the switch.",
    "The only thing we have to fear is fear itself.",
]

SAMPLE_RATE = 24000  # Required by Qwen3-TTS training


def record_one(output_path: Path, duration: int = 10) -> bool:
    """Record a single utterance via arecord. Returns True on success."""
    try:
        subprocess.run(
            [
                "arecord",
                "-f", "S16_LE",
                "-r", str(SAMPLE_RATE),
                "-c", "1",
                "-d", str(duration),
                str(output_path),
            ],
            check=True,
        )
        return True
    except (subprocess.CalledProcessError, FileNotFoundError) as e:
        print(f"  Recording failed: {e}", file=sys.stderr)
        return False


def main():
    parser = argparse.ArgumentParser(description="Record voice samples for TTS training")
    parser.add_argument("--output", "-o", required=True, help="Output directory")
    parser.add_argument("--speaker", "-s", required=True, help="Speaker name")
    parser.add_argument("--prompts-file", default=None, help="File with one prompt per line (optional)")
    parser.add_argument("--num", "-n", type=int, default=10, help="Number of utterances to record")
    parser.add_argument("--duration", "-d", type=int, default=10, help="Max seconds per recording")
    parser.add_argument("--ref-index", type=int, default=0, help="Which recording to use as ref_audio (default: 0)")
    args = parser.parse_args()

    out_dir = Path(args.output)
    out_dir.mkdir(parents=True, exist_ok=True)

    # Load prompts
    if args.prompts_file:
        prompts = Path(args.prompts_file).read_text().strip().splitlines()
    else:
        prompts = DEFAULT_PROMPTS

    prompts = prompts[: args.num]

    print(f"Recording {len(prompts)} utterances for speaker '{args.speaker}'")
    print(f"Output: {out_dir}")
    print(f"Sample rate: {SAMPLE_RATE} Hz, max duration: {args.duration}s")
    print()

    recordings = []

    for i, prompt in enumerate(prompts):
        wav_path = out_dir / f"{args.speaker}_{i:04d}.wav"
        print(f"--- [{i + 1}/{len(prompts)}] ---")
        print(f"  Read aloud: \"{prompt}\"")
        input("  Press Enter to start recording...")

        if record_one(wav_path, args.duration):
            recordings.append({"audio": str(wav_path), "text": prompt})
            print(f"  Saved: {wav_path}")
        else:
            print("  Skipped.")
        print()

    if not recordings:
        print("No recordings made. Exiting.")
        sys.exit(1)

    # Use the specified recording as ref_audio for all entries
    ref_audio = recordings[min(args.ref_index, len(recordings) - 1)]["audio"]
    for rec in recordings:
        rec["ref_audio"] = ref_audio

    jsonl_path = out_dir / "train.jsonl"
    with open(jsonl_path, "w") as f:
        for rec in recordings:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")

    print(f"Done! {len(recordings)} recordings saved.")
    print(f"Training JSONL: {jsonl_path}")
    print(f"Reference audio: {ref_audio}")
    print()
    print("Next steps:")
    print(f"  1. bash scripts/prepare_data.sh {jsonl_path} {out_dir}/prepared.jsonl")
    print(f"  2. bash scripts/train.sh {out_dir}/prepared.jsonl {args.speaker} 10")


if __name__ == "__main__":
    main()
