#!/usr/bin/env python3
"""Magpie TTS speech synthesis CLI.

Sends requests to NVIDIA Magpie TTS NIM and plays the returned audio.

Usage:
    uv run scripts/speak.py --message "Hello world"
    uv run scripts/speak.py --message "Great news!" --voice Mia.Happy
    uv run scripts/speak.py --message "Hi" --voice Aria
"""

import argparse
import os
import subprocess
import sys
import tempfile

import httpx

DEFAULT_SERVER_URL = "http://localhost:9000"

VOICES = [
    "Mia", "Mia.Neutral", "Mia.Calm", "Mia.Angry", "Mia.Happy", "Mia.Sad",
    "Aria", "Aria.Neutral", "Aria.Calm", "Aria.Angry", "Aria.Happy", "Aria.Sad", "Aria.Fearful",
    "Jason", "Jason.Neutral", "Jason.Calm", "Jason.Angry", "Jason.Happy",
    "Leo", "Leo.Neutral", "Leo.Calm", "Leo.Angry", "Leo.Sad", "Leo.Fearful",
]

VOICE_PREFIX = "Magpie-Multilingual.EN-US."


def speak(
    message: str,
    voice: str = "Mia.Calm",
    language: str = "en-US",
    speed: int = 125,
    server_url: str = DEFAULT_SERVER_URL,
):
    """Synthesize speech via Magpie TTS NIM and play it."""
    url = f"{server_url.rstrip('/')}/v1/audio/synthesize"

    full_voice = f"{VOICE_PREFIX}{voice}" if not voice.startswith("Magpie-") else voice

    # Wrap in SSML prosody if speed != 100
    text = message
    if speed != 100:
        text = f'<speak><prosody rate="{speed}%">{message}</prosody></speak>'

    try:
        resp = httpx.post(
            url,
            data={"language": language, "text": text, "voice": full_voice},
            timeout=120.0,
        )
    except httpx.ConnectError:
        print(
            f"Error: Cannot connect to Magpie TTS at {server_url}\n"
            "Start the server with: docker compose up magpie-tts",
            file=sys.stderr,
        )
        sys.exit(1)

    if resp.status_code != 200:
        print(f"Error: Server returned {resp.status_code}: {resp.text}", file=sys.stderr)
        sys.exit(1)

    # Check for JSON error responses
    content_type = resp.headers.get("content-type", "")
    if "json" in content_type or resp.content[:1] == b"{":
        print(f"Error: Server returned error: {resp.text}", file=sys.stderr)
        sys.exit(1)

    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
        f.write(resp.content)
        tmp_path = f.name

    try:
        subprocess.run(["aplay", tmp_path], check=True)
    finally:
        os.unlink(tmp_path)


def main():
    parser = argparse.ArgumentParser(description="Magpie TTS speech synthesis")
    parser.add_argument("--message", "-m", required=True, help="Text to speak")
    parser.add_argument("--voice", "-v", default="Mia.Calm", choices=VOICES,
                        help="Voice name (default: Mia.Calm)")
    parser.add_argument("--language", "-l", default="en-US",
                        help="Language code (default: en-US)")
    parser.add_argument("--speed", "-s", type=int, default=125,
                        help="Speech speed percentage (default: 125)")
    parser.add_argument("--server-url", default=os.environ.get("MAGPIE_TTS_URL", DEFAULT_SERVER_URL),
                        help=f"Magpie TTS server URL (env: MAGPIE_TTS_URL, default: {DEFAULT_SERVER_URL})")
    args = parser.parse_args()

    speak(
        message=args.message,
        voice=args.voice,
        language=args.language,
        speed=args.speed,
        server_url=args.server_url,
    )


if __name__ == "__main__":
    main()
