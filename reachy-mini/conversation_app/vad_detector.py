#!/usr/bin/env python3
"""
Voice Activity Detection (VAD) Module

This module provides voice activity detection using WebRTC VAD.
"""

import webrtcvad
import logging
from typing import Optional

logger = logging.getLogger(__name__)


class VADDetector:
    """Voice Activity Detector using WebRTC VAD"""
    
    def __init__(self, aggressiveness: int = 3, sample_rate: int = 16000):
        """
        Initialize VAD detector
        
        Args:
            aggressiveness: VAD aggressiveness level (0-3, where 3 is most aggressive)
            sample_rate: Audio sample rate in Hz
        """
        self.sample_rate = sample_rate
        self.aggressiveness = aggressiveness
        
        try:
            self.vad = webrtcvad.Vad(aggressiveness)
            logger.info(f"VAD initialized with aggressiveness={aggressiveness}, rate={sample_rate}Hz")
        except Exception as e:
            logger.error(f"Failed to initialize VAD: {e}")
            raise
    
    def is_speech(self, audio_data: bytes) -> bool:
        """
        Check if audio data contains speech
        
        Args:
            audio_data: Raw audio data as bytes
            
        Returns:
            True if speech is detected, False otherwise
        """
        try:
            result = self.vad.is_speech(audio_data, self.sample_rate)
            #logger.debug(f"VAD result: {'SPEECH' if result else 'SILENCE'}")
            return result
        except Exception as e:
            logger.error(f"Error in VAD processing: {e}")
            return False
    
    def set_aggressiveness(self, aggressiveness: int):
        """
        Update VAD aggressiveness level
        
        Args:
            aggressiveness: New aggressiveness level (0-3)
        """
        if not 0 <= aggressiveness <= 3:
            raise ValueError("Aggressiveness must be between 0 and 3")
        
        self.aggressiveness = aggressiveness
        self.vad.set_mode(aggressiveness)
        logger.info(f"VAD aggressiveness updated to {aggressiveness}")
