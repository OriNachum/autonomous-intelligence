"""PCM16/WAV conversion, resampling between sample rates."""

from __future__ import annotations

import base64
import io
import struct
import wave

import numpy as np
from scipy.signal import resample

from .protocol import CLIENT_SAMPLE_RATE, STT_SAMPLE_RATE, TTS_SAMPLE_RATE, VAD_SAMPLE_RATE


def pcm16_to_numpy(pcm_bytes: bytes) -> np.ndarray:
    """Convert raw PCM16 LE bytes to int16 numpy array."""
    return np.frombuffer(pcm_bytes, dtype=np.int16)


def numpy_to_pcm16(arr: np.ndarray) -> bytes:
    """Convert int16 numpy array to raw PCM16 LE bytes."""
    return arr.astype(np.int16).tobytes()


def resample_pcm16(pcm_bytes: bytes, from_rate: int, to_rate: int) -> bytes:
    """Resample raw PCM16 bytes from one sample rate to another."""
    if from_rate == to_rate:
        return pcm_bytes
    samples = pcm16_to_numpy(pcm_bytes).astype(np.float32)
    num_out = int(len(samples) * to_rate / from_rate)
    resampled = resample(samples, num_out)
    np.clip(resampled, -32768, 32767, out=resampled)
    return resampled.astype(np.int16).tobytes()


def client_pcm16_to_wav_16k(pcm_bytes: bytes) -> bytes:
    """Convert client PCM16 24kHz to WAV 16kHz for Parakeet STT."""
    resampled = resample_pcm16(pcm_bytes, CLIENT_SAMPLE_RATE, STT_SAMPLE_RATE)
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(STT_SAMPLE_RATE)
        wf.writeframes(resampled)
    return buf.getvalue()


def tts_pcm16_to_client_base64(pcm_bytes: bytes) -> str:
    """Convert Magpie PCM16 22050Hz to PCM16 24kHz base64 for client."""
    resampled = resample_pcm16(pcm_bytes, TTS_SAMPLE_RATE, CLIENT_SAMPLE_RATE)
    return base64.b64encode(resampled).decode("ascii")


def client_pcm16_to_vad_float32(pcm_bytes: bytes) -> np.ndarray:
    """Convert client PCM16 24kHz to float32 tensor at 16kHz for Silero VAD."""
    resampled = resample_pcm16(pcm_bytes, CLIENT_SAMPLE_RATE, VAD_SAMPLE_RATE)
    samples = pcm16_to_numpy(resampled)
    return samples.astype(np.float32) / 32768.0


def decode_audio_appendix(audio_b64: str) -> bytes:
    """Decode base64 audio from client input_audio_buffer.append event."""
    return base64.b64decode(audio_b64)
