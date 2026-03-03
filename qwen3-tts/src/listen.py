#!/usr/bin/env python3
"""Speech-to-text CLI using NVIDIA Parakeet TDT via containerized server.

Records audio from the microphone and transcribes it using Parakeet 0.6B.

Usage:
    uv run src/listen.py
    uv run src/listen.py --duration 10
    uv run src/listen.py --file recording.wav
"""

import argparse
import os
import subprocess
import sys
import tempfile

import httpx

DEFAULT_SERVER_URL = "http://localhost:9002"
SAMPLE_RATE = 16000


def record_audio(duration: int = 5) -> str:
    """Record audio from microphone, return path to WAV file."""
    tmp = tempfile.NamedTemporaryFile(suffix=".wav", delete=False)
    tmp.close()
    try:
        subprocess.run(
            ["arecord", "-f", "S16_LE", "-r", str(SAMPLE_RATE), "-c", "1",
             "-d", str(duration), tmp.name],
            check=True,
        )
    except FileNotFoundError:
        print("Error: arecord not found. Install alsa-utils.", file=sys.stderr)
        os.unlink(tmp.name)
        sys.exit(1)
    except subprocess.CalledProcessError as e:
        print(f"Error recording audio: {e}", file=sys.stderr)
        os.unlink(tmp.name)
        sys.exit(1)
    return tmp.name


def transcribe(
    audio_path: str,
    language: str = "en",
    server_url: str = DEFAULT_SERVER_URL,
) -> str:
    """Send audio to Parakeet ASR server and return transcription."""
    url = f"{server_url.rstrip('/')}/v1/audio/transcriptions"

    with open(audio_path, "rb") as f:
        try:
            resp = httpx.post(
                url,
                data={"language": language},
                files={"file": ("audio.wav", f, "audio/wav")},
                timeout=60.0,
            )
        except httpx.ConnectError:
            print(
                f"Error: Cannot connect to Parakeet ASR at {server_url}\n"
                "Start the server with: docker compose up -d parakeet-asr",
                file=sys.stderr,
            )
            sys.exit(1)

    if resp.status_code != 200:
        print(f"Error: Server returned {resp.status_code}: {resp.text}", file=sys.stderr)
        sys.exit(1)

    return resp.json().get("text", "")


def listen(
    duration: int = 5,
    audio_file: str | None = None,
    language: str = "en",
    server_url: str = DEFAULT_SERVER_URL,
) -> str:
    """Record (or use existing file) and transcribe."""
    if audio_file:
        return transcribe(os.path.expanduser(audio_file), language, server_url)

    print(f"Recording for {duration} seconds... speak now!", file=sys.stderr)
    audio_path = record_audio(duration)
    try:
        return transcribe(audio_path, language, server_url)
    finally:
        os.unlink(audio_path)


def main():
    parser = argparse.ArgumentParser(description="Parakeet ASR speech-to-text")
    parser.add_argument("--duration", "-d", type=int, default=5,
                        help="Recording duration in seconds (default: 5)")
    parser.add_argument("--file", "-f", default=None,
                        help="Transcribe existing audio file instead of recording")
    parser.add_argument("--language", "-l", default="en",
                        help="Language code (default: en)")
    parser.add_argument("--server-url", default=os.environ.get("PARAKEET_ASR_URL", DEFAULT_SERVER_URL),
                        help=f"Parakeet ASR server URL (env: PARAKEET_ASR_URL, default: {DEFAULT_SERVER_URL})")
    args = parser.parse_args()

    text = listen(
        duration=args.duration,
        audio_file=args.file,
        language=args.language,
        server_url=args.server_url,
    )

    if text.strip():
        print(text)
    else:
        print("(no speech detected)", file=sys.stderr)


if __name__ == "__main__":
    main()
