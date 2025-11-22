#!/usr/bin/env python3
"""
Speech-to-Text (STT) Module using Faster Whisper

This module provides speech-to-text transcription using faster-whisper.
"""

import numpy as np
import wave
import tempfile
import os
import logging
from pathlib import Path
from typing import Optional, List
from faster_whisper import WhisperModel

logger = logging.getLogger(__name__)


class WhisperSTT:
    """Speech-to-Text using Faster Whisper"""
    
    def __init__(
        self,
        model_size: str = "base",
        device: str = "cpu",
        compute_type: str = "int8",
        language: str = "en"
    ):
        """
        Initialize Whisper STT
        
        Args:
            model_size: Whisper model size (tiny, base, small, medium, large)
            device: Device to run on (cpu, cuda)
            compute_type: Compute type (float16, float32, int8)
            language: Language code for transcription
        """
        self.model_size = model_size
        self.device = device
        
        # Force int8 for CPU to avoid SGEMM backend issues
        if device == "cpu" and compute_type == "float16":
            logger.warning("float16 not supported on CPU, switching to int8")
            compute_type = "int8"
        
        self.compute_type = compute_type
        self.language = language
        
        logger.info(f"Loading Whisper model: {model_size} on {device} with {compute_type}")
        
        try:
            self.model = WhisperModel(
                model_size,
                device=device,
                compute_type=compute_type
            )
            logger.info("Whisper model loaded successfully")
        except Exception as e:
            logger.error(f"Failed to load Whisper model: {e}")
            raise
    
    def transcribe(
        self,
        audio_file_path: str,
        language: Optional[str] = None,
        beam_size: int = 5
    ) -> Optional[str]:
        """
        Transcribe audio file
        
        Args:
            audio_file_path: Path to audio file (WAV format)
            language: Language code (uses default if not specified)
            beam_size: Beam size for transcription
            
        Returns:
            Transcribed text or None if transcription fails
        """
        lang = language or self.language
        
        try:
            logger.info(f"Starting transcription of {audio_file_path}")
            
            segments, info = self.model.transcribe(
                audio_file_path,
                language=lang,
                beam_size=beam_size
            )
            
            # Collect all segments into a single transcription
            transcription_parts = []
            for segment in segments:
                text = segment.text.strip()
                if text:
                    transcription_parts.append(text)
            
            transcription = " ".join(transcription_parts).strip()
            
            logger.info(f"Transcription complete: '{transcription}'")
            return transcription if transcription else None
            
        except Exception as e:
            logger.error(f"Error during transcription: {e}", exc_info=True)
            return None
    
    def transcribe_audio_data(
        self,
        audio_chunks: List[np.ndarray],
        sample_rate: int,
        sample_width: int = 2,
        language: Optional[str] = None,
        beam_size: int = 5
    ) -> Optional[str]:
        """
        Transcribe audio from numpy arrays
        
        Args:
            audio_chunks: List of numpy arrays containing audio data
            sample_rate: Audio sample rate in Hz
            sample_width: Sample width in bytes (default 2 for int16)
            language: Language code (uses default if not specified)
            beam_size: Beam size for transcription
            
        Returns:
            Transcribed text or None if transcription fails
        """
        if not audio_chunks:
            logger.warning("No audio data provided for transcription")
            return None
        
        try:
            # Combine audio chunks
            combined_audio = np.concatenate(audio_chunks)
            
            # Create a temporary WAV file
            with tempfile.NamedTemporaryFile(suffix='.wav', delete=False) as temp_wav:
                temp_wav_path = temp_wav.name
            
            try:
                # Write audio to temporary file
                self._save_audio_to_wav(
                    combined_audio,
                    temp_wav_path,
                    sample_rate,
                    sample_width
                )
                
                # Transcribe the temporary file
                return self.transcribe(temp_wav_path, language, beam_size)
                
            finally:
                # Clean up temporary file
                try:
                    os.unlink(temp_wav_path)
                except Exception as e:
                    logger.warning(f"Failed to delete temporary file {temp_wav_path}: {e}")
        
        except Exception as e:
            logger.error(f"Error in transcribe_audio_data: {e}", exc_info=True)
            return None
    
    def _save_audio_to_wav(
        self,
        audio_data: np.ndarray,
        filename: str,
        sample_rate: int,
        sample_width: int = 2
    ):
        """
        Save audio data to WAV file
        
        Args:
            audio_data: Numpy array containing audio data
            filename: Output filename
            sample_rate: Audio sample rate in Hz
            sample_width: Sample width in bytes
        """
        with wave.open(filename, 'wb') as wav_file:
            wav_file.setnchannels(1)
            wav_file.setsampwidth(sample_width)
            wav_file.setframerate(sample_rate)
            wav_file.writeframes(audio_data.tobytes())
        
        logger.debug(f"Saved audio to {filename}")
    
    def set_language(self, language: str):
        """
        Update the default language for transcription
        
        Args:
            language: Language code
        """
        self.language = language
        logger.info(f"Language updated to {language}")
