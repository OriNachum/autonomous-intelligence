#!/usr/bin/env python3
"""
Direction of Audio (DOA) Detection Module

This module provides DOA detection using the ReachyMini library.
It handles continuous DOA sampling and averaging during speech segments.
"""

import logging
import numpy as np
import time
from typing import Optional, Tuple, Dict
from reachy_mini import ReachyMini
from reachy_mini.utils import create_head_pose
from reachy_mini.utils.interpolation import InterpolationTechnique, minimum_jerk

logger = logging.getLogger(__name__)


class ReachyController:
    """Direction of Audio Detector using ReachyMini"""
    
    def __init__(self, smoothing_alpha: float = 0.1, log_level: int = logging.DEBUG):
        """
        Initialize DOA detector
        
        Args:
            smoothing_alpha: Smoothing factor for exponential moving average (0-1)
                           Lower values = more smoothing, higher = more responsive
            log_level: Logging level for ReachyMini
        """
        self.smoothing_alpha = smoothing_alpha
        
        # Initialize ReachyMini
        logger.info("Initializing ReachyMini for DOA detection...")
        try:
            self.mini = ReachyMini(timeout=10.0, spawn_daemon=True, log_level=log_level, automatic_body_yaw=True,)
            logger.info("ReachyMini initialized successfully")
        except Exception as e:
            logger.error(f"Failed to initialize ReachyMini: {e}")
            raise
        
        # Circular averaging state (cartesian coordinates)
        self.avg_x = 0.0
        self.avg_y = 0.0
        self.sample_count = 0
        
        # Current DOA state
        self.current_doa = None
        
        logger.info(f"DOA Detector initialized with smoothing_alpha={smoothing_alpha}")
    
    def get_current_doa(self) -> Tuple[float, bool]:
        """
        Get current Direction of Audio from ReachyMini
        
        Returns:
            Tuple of (angle_radians, is_speech_detected)
            - angle_radians: DOA angle in radians
            - is_speech_detected: Boolean indicating if speech/audio detected
        """
        try:
            doa = self.mini.media.audio.get_DoA()
            self.current_doa = doa
            
            # Log the raw values
            logger.info(f"DOA raw values: angle={doa[0]:.4f} rad ({np.degrees(doa[0]):.1f}°), "
                        f"is_speech_detected={doa[1]}")
            
            return doa
        except Exception as e:
            logger.error(f"Error getting DOA: {e}", exc_info=True)
            return (0.0, False)
    
    def start_speech_segment(self):
        """Clear DOA buffer and reset averaging for new speech segment"""
        self.avg_x = 0.0
        self.avg_y = 0.0
        self.sample_count = 0
        logger.info("DOA buffer cleared for new speech segment")
    
    def add_doa_sample(self, doa_tuple: Tuple[float, bool]):
        """
        Add DOA sample to running average using exponential moving average
        in cartesian space to handle circular values correctly
        
        Args:
            doa_tuple: Tuple of (angle_radians, is_speech_detected)
        """
        angle, is_speech_detected = doa_tuple
        
        # Only add samples where speech/audio is detected
        if not is_speech_detected:
            logger.debug("Skipping DOA sample - no speech detected")
            return
        
        # Convert to cartesian coordinates
        new_x = np.cos(angle)
        new_y = np.sin(angle)
        
        # Apply exponential moving average
        if self.sample_count == 0:
            # First sample - initialize
            self.avg_x = new_x
            self.avg_y = new_y
        else:
            # Apply EMA
            self.avg_x = self.smoothing_alpha * new_x + (1 - self.smoothing_alpha) * self.avg_x
            self.avg_y = self.smoothing_alpha * new_y + (1 - self.smoothing_alpha) * self.avg_y
        
        self.sample_count += 1
        
        # Calculate current average angle for logging
        current_avg_angle = np.arctan2(self.avg_y, self.avg_x)
        logger.debug(f"DOA sample added: new_angle={np.degrees(angle):.1f}°, "
                    f"avg_angle={np.degrees(current_avg_angle):.1f}° "
                    f"(sample #{self.sample_count})")
    
    def get_average_doa(self) -> Optional[Dict]:
        """
        Get average DOA from all samples in current speech segment
        
        Returns:
            Dict with average DOA info, or None if no valid samples:
            {
                "angle_radians": float,
                "angle_degrees": float,
                "sample_count": int,
                "cartesian_x": float,
                "cartesian_y": float
            }
        """
        if self.sample_count == 0:
            logger.debug("No DOA samples to average")
            return None
        
        # Convert back to angle from cartesian coordinates
        avg_angle_radians = np.arctan2(self.avg_y, self.avg_x)
        avg_angle_degrees = np.degrees(avg_angle_radians)
        
        result = {
            "angle_radians": float(avg_angle_radians),
            "angle_degrees": float(avg_angle_degrees),
            "sample_count": self.sample_count,
            "cartesian_x": float(self.avg_x),
            "cartesian_y": float(self.avg_y)
        }
        
        logger.debug(f"Average DOA calculated: {avg_angle_degrees:.1f}° from {self.sample_count} samples")
        
        return result
    
    def get_current_doa_dict(self) -> Optional[Dict]:
        """
        Get current DOA as a dictionary with detailed information
        
        Returns:
            Dict with current DOA info, or None if no current DOA:
            {
                "angle_radians": float,
                "angle_degrees": float,
                "is_speech_detected": bool
            }
        """
        if self.current_doa is None:
            return None
        
        return {
            "angle_radians": float(self.current_doa[0]),
            "angle_degrees": float(np.degrees(self.current_doa[0])),
            "is_speech_detected": bool(self.current_doa[1])
        }
    
    def start_recording(self):
        """Start recording audio via ReachyMini"""
        try:
            self.mini.media.start_recording()
            logger.info("Recording started via ReachyMini")
        except Exception as e:
            logger.error(f"Error starting recording: {e}", exc_info=True)
            raise
    
    def stop_recording(self):
        """Stop recording audio via ReachyMini"""
        try:
            self.mini.media.stop_recording()
            logger.info("Recording stopped via ReachyMini")
        except Exception as e:
            logger.error(f"Error stopping recording: {e}", exc_info=True)
            raise
    
    def get_audio_sample(self) -> Optional[np.ndarray]:
        """
        Get audio sample from ReachyMini
        
        ReachyMini returns stereo audio (2 channels):
        - Channel 0: AEC-processed microphone (echo-cancelled)
        - Channel 1: Reference/playback signal
        
        We extract only Channel 0 for speech detection/transcription.
        
        Returns:
            Audio sample as mono numpy array (1D), or None if no sample available
        """
        try:
            sample = self.mini.media.get_audio_sample()
            if sample is None:
                return None
            
            # Check if this is stereo audio (shape: (N, 2))
            if len(sample.shape) == 2 and sample.shape[1] == 2:
                # Extract Channel 0 (AEC-processed channel)
                mono_sample = sample[:, 0]
                logger.debug(f"Converted stereo audio {sample.shape} to mono {mono_sample.shape} (Channel 0)")
                return mono_sample
            elif len(sample.shape) == 1:
                # Already mono
                logger.debug(f"Got mono audio sample with shape: {sample.shape}")
                return sample
            else:
                logger.warning(f"Unexpected audio shape: {sample.shape}, returning as-is")
                return sample
                
        except Exception as e:
            logger.error(f"Error getting audio sample: {e}", exc_info=True)
            return None
    
    def move_to(self,duration=1.0, method=InterpolationTechnique.CARTOON, roll=0.0, pitch=0.0, yaw=0.0, antennas=[0.0, 0.0], body_yaw=0.0):
        """
        Move the robot to a target head pose and/or antennas position and/or body direction.
        """
        (safe_roll, safe_pitch, safe_yaw, safe_antennas, safe_body_yaw) = self.apply_safety_to_movement(roll, pitch, yaw, antennas, body_yaw)
        self.mini.goto_target(create_head_pose(roll=safe_roll, pitch=safe_pitch, yaw=safe_yaw), antennas=safe_antennas, duration=duration, method=method, body_yaw=safe_body_yaw)
    
    def move_cyclicly(self, duration=1.0, repeatitions=1, roll=0.0, pitch=0.0, yaw=0.0, antennas=[0.0, 0.0], body_yaw=0.0):
        """
        A cyclical movement
        """
        for _ in range(1):
            t = time.time()
            self.move_smoothly(duration=duration/2, offset=0, roll=roll, pitch=pitch, yaw=yaw, antennas=antennas, body_yaw=body_yaw)
            self.move_smoothly(duration=duration/2, offset=1, roll=roll, pitch=pitch, yaw=yaw, antennas=antennas, body_yaw=body_yaw)

        
    def move_smoothly(self, duration=1.0, offset=0, roll=0.0, pitch=0.0, yaw=0.0, antennas=[0.0, 0.0], body_yaw=0.0):
        """
        Move the robot smoothly to a single position.
        """
        def smooth_movement(t, max_angle, offset=0):
            return np.deg2rad(max_angle * np.sin((2*offset + 2) * np.pi * 0.5 * t ))
        
        logger.info(f"Moving robot smoothly to: roll={roll}, pitch={pitch}, yaw={yaw}, antennas={antennas}, body_yaw={body_yaw}")  
        start_time = time.time()
        t = time.time()
        while t - start_time < duration:
            tick_in_time = t - start_time
            body_yaw_t = smooth_movement(tick_in_time, body_yaw, offset)
            antennas_t = [smooth_movement(tick_in_time, antennas[0], offset), smooth_movement(tick_in_time, antennas[1], offset)]
            pitch_t = smooth_movement(tick_in_time, pitch, offset)
            roll_t = smooth_movement(tick_in_time, roll, offset)
            yaw_t = smooth_movement(tick_in_time, yaw, offset)

            (safe_roll, safe_pitch, safe_yaw, safe_antennas, safe_body_yaw) = self.apply_safety_to_movement(roll_t, pitch_t, yaw_t, antennas=antennas_t, body_yaw=body_yaw_t)

            head_pose = create_head_pose(
                roll=safe_roll,
                pitch=safe_pitch,
                yaw=safe_yaw,
                degrees=False,
                mm=False,
            )
            self.mini.set_target(head=head_pose, antennas=safe_antennas, body_yaw=safe_body_yaw)
            t = time.time()

    def apply_safety_to_movement(self, roll, pitch, yaw, antennas, body_yaw):
        """
        Apply safety limits to robot movements.
        
        - Head yaw is limited to ±40 degrees
        - Overflow beyond ±40 degrees is redirected to body_yaw
        """
        HEAD_YAW_LIMIT = np.deg2rad(40.0)  # 40 degrees in radians
        
        safe_roll = roll
        safe_pitch = pitch
        safe_antennas = antennas
        
        # Handle head yaw overflow by redirecting to body_yaw
        if abs(yaw) > HEAD_YAW_LIMIT:
            # Calculate overflow amount
            overflow = yaw - np.sign(yaw) * HEAD_YAW_LIMIT
            
            # Limit head yaw to maximum allowed
            safe_yaw = np.sign(yaw) * HEAD_YAW_LIMIT
            
            # Add overflow to body_yaw
            safe_body_yaw = body_yaw + overflow
            
            logger.debug(f"Head yaw limited: requested={np.degrees(yaw):.1f}°, "
                        f"safe_yaw={np.degrees(safe_yaw):.1f}°, "
                        f"overflow={np.degrees(overflow):.1f}° redirected to body_yaw")
        else:
            safe_yaw = yaw
            safe_body_yaw = body_yaw

        return (safe_roll, safe_pitch, safe_yaw, safe_antennas, safe_body_yaw)


    def get_sample_rate(self) -> int:
        """
        Get audio sample rate from ReachyMini
        
        Returns:
            Sample rate in Hz
        """
        try:
            sample_rate = self.mini.media.get_input_audio_samplerate()
            logger.debug(f"Sample rate: {sample_rate} Hz")
            return sample_rate
        except Exception as e:
            logger.error(f"Error getting sample rate: {e}", exc_info=True)
            return 16000  # Default fallback
    
    def cleanup(self):
        """Clean up ReachyMini resources"""
        logger.info("Cleaning up DOA detector resources...")
        if hasattr(self, 'mini') and self.mini is not None:
            try:
                # ReachyMini context manager handles cleanup
                self.mini.__exit__(None, None, None)
                logger.info("ReachyMini cleaned up successfully")
            except Exception as e:
                logger.error(f"Error cleaning up ReachyMini: {e}")
