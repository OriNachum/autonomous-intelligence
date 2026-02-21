#!/usr/bin/env python3
"""MagpieTTS speech synthesis CLI.

Sends requests to the MagpieTTS Docker service and plays the returned audio.

Usage:
    uv run src/speak.py --message "Hello world"
    uv run src/speak.py --message "Hola mundo" --language es --speaker Sofia
    uv run src/speak.py --message "Hi" --server-url http://myhost:8100
"""

import argparse
import os
import subprocess
import sys
import tempfile

import httpx

DEFAULT_SERVER_URL = "http://localhost:8100"

SPEAKERS = ["John", "Sofia", "Aria", "Jason", "Leo"]
LANGUAGES = ["en", "es", "de", "fr", "vi", "it", "zh"]


def speak(
    message: str,
    speaker: str = "Aria",
    language: str = "en",
    server_url: str = DEFAULT_SERVER_URL,
):
    """Synthesize speech via the MagpieTTS service and play it."""
    url = f"{server_url.rstrip('/')}/synthesize"

    try:
        resp = httpx.post(
            url,
            json={"message": message, "speaker": speaker, "language": language},
            timeout=60.0,
        )
    except httpx.ConnectError:
        print(
            f"Error: Cannot connect to MagpieTTS service at {server_url}\n"
            "Start the service with: docker compose up -d",
            file=sys.stderr,
        )
        sys.exit(1)

    if resp.status_code != 200:
        print(f"Error: Service returned {resp.status_code}: {resp.text}", file=sys.stderr)
        sys.exit(1)

    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
        f.write(resp.content)
        tmp_path = f.name

    try:
        subprocess.run(["aplay", tmp_path], check=True)
    finally:
        os.unlink(tmp_path)


def main():
    parser = argparse.ArgumentParser(description="MagpieTTS speech synthesis")
    parser.add_argument("--message", "-m", required=True, help="Text to speak")
    parser.add_argument("--speaker", "-s", default="Aria", choices=SPEAKERS,
                        help="Speaker voice (default: Aria)")
    parser.add_argument("--language", "-l", default="en", choices=LANGUAGES,
                        help="Language code (default: en)")
    parser.add_argument("--server-url", default=os.environ.get("MAGPIETTS_URL", DEFAULT_SERVER_URL),
                        help=f"MagpieTTS service URL (env: MAGPIETTS_URL, default: {DEFAULT_SERVER_URL})")
    args = parser.parse_args()

    speak(
        message=args.message,
        speaker=args.speaker,
        language=args.language,
        server_url=args.server_url,
    )


if __name__ == "__main__":
    main()
