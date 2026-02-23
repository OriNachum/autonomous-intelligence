#!/usr/bin/env python3
"""Direct Qwen3-TTS inference via qwen-tts (no vLLM-Omni server needed).

Bypasses the vLLM-Omni pipeline for ground-truth audio quality comparison.

Usage:
    uv run src/speak_direct.py --message "Hello world"
    uv run src/speak_direct.py --message "Great news!" --voice Vivian --instruct "excited"
"""

import argparse
import os
import subprocess
import tempfile

import torch
import soundfile as sf
from qwen_tts import Qwen3TTSModel

CUSTOM_VOICE_MODEL = "Qwen/Qwen3-TTS-12Hz-1.7B-CustomVoice"
BASE_MODEL = "Qwen/Qwen3-TTS-12Hz-1.7B-Base"

SPEAKERS = ["Vivian", "Ryan", "Aiden", "Dylan", "Eric", "Ono_Anna", "Serena", "Sohee", "Uncle_Fu"]


def speak_direct(
    message: str,
    voice: str = "Vivian",
    instruct: str = "",
    language: str = "English",
    task_type: str = "CustomVoice",
    ref_audio: str | None = None,
    ref_text: str | None = None,
    output: str | None = None,
    play: bool = True,
):
    """Synthesize speech directly via qwen-tts and play it."""
    if task_type == "CustomVoice":
        model = Qwen3TTSModel.from_pretrained(
            CUSTOM_VOICE_MODEL,
            device_map="cuda:0",
            dtype=torch.bfloat16,
        )
        wavs, sr = model.generate_custom_voice(
            text=message,
            language=language,
            speaker=voice,
            instruct=instruct,
            max_new_tokens=2048,
            temperature=0.3,
            top_k=50,
            top_p=0.85,
            repetition_penalty=1.0,
        )
    elif task_type == "Base":
        model = Qwen3TTSModel.from_pretrained(
            BASE_MODEL,
            device_map="cuda:0",
            dtype=torch.bfloat16,
        )
        wavs, sr = model.generate_voice_clone(
            text=message,
            language=language,
            ref_audio=ref_audio,
            ref_text=ref_text,
        )
    else:
        raise ValueError(f"Unknown task type: {task_type}")

    if output:
        sf.write(output, wavs[0], sr)
        print(f"Saved to {output}")

    if play:
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
            sf.write(f.name, wavs[0], sr)
            tmp_path = f.name
        try:
            subprocess.run(["aplay", tmp_path], check=True)
        finally:
            os.unlink(tmp_path)


def main():
    parser = argparse.ArgumentParser(description="Qwen3-TTS direct inference (no server)")
    parser.add_argument("--message", "-m", required=True, help="Text to speak")
    parser.add_argument("--voice", "-v", default="Vivian", choices=SPEAKERS,
                        help="Speaker name (default: Vivian)")
    parser.add_argument("--instruct", "-i", default="", help="Emotion/style instruction")
    parser.add_argument("--language", "-l", default="English")
    parser.add_argument("--task-type", "-t", default="CustomVoice",
                        choices=["CustomVoice", "Base"])
    parser.add_argument("--ref-audio", default=None, help="Reference audio for cloning")
    parser.add_argument("--ref-text", default=None, help="Transcript of reference audio")
    parser.add_argument("--output", "-o", default=None, help="Save WAV to file")
    parser.add_argument("--no-play", action="store_true", help="Don't play audio")
    args = parser.parse_args()

    speak_direct(
        message=args.message,
        voice=args.voice,
        instruct=args.instruct,
        language=args.language,
        task_type=args.task_type,
        ref_audio=args.ref_audio,
        ref_text=args.ref_text,
        output=args.output,
        play=not args.no_play,
    )


if __name__ == "__main__":
    main()
