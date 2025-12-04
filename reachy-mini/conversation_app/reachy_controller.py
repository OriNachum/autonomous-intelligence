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
from scipy.spatial.transform import Rotation
from .safety_manager import SafetyManager, SafetyConfig
from . import mappings

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
            self.mini = ReachyMini(timeout=10.0,
                                   spawn_daemon=True,
                                   log_level=log_level,
                                   automatic_body_yaw=True,
                                   media_backend='gstreamer')
            self.reachy_is_awake = True
            logger.info("ReachyMini initialized successfully")
        except Exception as e:
            logger.error(f"Failed to initialize ReachyMini: {e}")
            raise
        
        # Circular averaging state (cartesian coordinates)
        self.avg_x = 0.0
        self.avg_y = 0.0
        self.sample_count = 0
        self.total_sample_count = 0
        self.speech_detected_count = 0

        # Current DOA state
        self.current_doa = None
        
        # Track body yaw state (not directly readable from ReachyMini)
        self._current_body_yaw = 0.0
        
        # Initialize safety manager with default configuration
        self.safety_config = SafetyConfig()
        self.safety_manager = SafetyManager(self.safety_config)
        
        logger.info(f"DOA Detector initialized with smoothing_alpha={smoothing_alpha}")
    
    def parse_compass_direction(self, direction_str: str) -> float:
        """
        Parse compass direction string and convert to Reachy yaw angle in degrees.
        Delegates to mappings module for consistency.
        
        Args:
            direction_str: Compass direction (e.g., "North", "East", "North East")
        
        Returns:
            Yaw angle in degrees for Reachy, clamped to ±45°
        """
        return mappings.parse_compass_direction(direction_str)
    
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
        self.total_sample_count = 0
        self.speech_detected_count = 0
        logger.info("DOA buffer cleared for new speech segment")
    
    def add_doa_sample(self, doa_tuple: Tuple[float, bool]):
        """
        Add DOA sample to running average using exponential moving average
        in cartesian space to handle circular values correctly
        
        Args:
            doa_tuple: Tuple of (angle_radians, is_speech_detected)
        """
        angle, is_speech_detected = doa_tuple
        self.total_sample_count += 1
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
        self.speech_detected_count += 1
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
            "cartesian_y": float(self.avg_y),
            "is_speech_detected": bool(self.speech_detected_count / self.total_sample_count > 0.7)
        }
        
        logger.info(f"Average DOA calculated: {avg_angle_degrees:.1f}° from {self.sample_count} samples")
        
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
    
    def get_current_state(self) -> Tuple[float, float, float, list, float]:
        """
        Get current robot state (pose and positions).
        
        Returns:
            Tuple of (roll, pitch, yaw, antennas, body_yaw) all in degrees
        """
        try:
            # Get current head pose as 4x4 transformation matrix
            head_pose_matrix = self.mini.get_current_head_pose()
            
            # Convert rotation matrix to Euler angles (in radians)
            rotation_matrix = head_pose_matrix[:3, :3]
            rotation = Rotation.from_matrix(rotation_matrix)
            # Get Euler angles in 'xyz' order (roll, pitch, yaw)
            euler_angles = rotation.as_euler('xyz', degrees=True)
            roll, pitch, yaw = euler_angles
            
            # Get antenna positions (in radians, convert to degrees)
            antennas_rad = self.mini.get_present_antenna_joint_positions()
            antennas = [np.degrees(antennas_rad[0]), np.degrees(antennas_rad[1])]
            
            # Use tracked body_yaw
            body_yaw = self._current_body_yaw
            
            logger.debug(f"Current state: roll={roll:.1f}°, pitch={pitch:.1f}°, yaw={yaw:.1f}°, "
                        f"antennas={antennas}, body_yaw={body_yaw:.1f}°")
            
            return (roll, pitch, yaw, antennas, body_yaw)
        except Exception as e:
            logger.error(f"Error getting current state: {e}", exc_info=True)
            # Return safe defaults
            return (0.0, 0.0, 0.0, [0.0, 0.0], 0.0)
    
    def get_current_state_natural(self) -> Dict[str, str]:
        """
        Get current robot state expressed in natural language.
        
        Returns:
            Dictionary with natural language descriptions:
            {
                "head_direction": "East" or "North" or "West" etc.,
                "head_tilt": "up" or "down" or "neutral",
                "head_roll": "left" or "right" or "neutral",
                "antennas": "happy" or "neutral" or "sad" etc.,
                "body_direction": "East" or "North" or "West" etc.
            }
        """
        roll, pitch, yaw, antennas, body_yaw = self.get_current_state()
        
        # Use mappings module to convert values to names
        head_direction = mappings.value_to_name('yaw', yaw)
        body_direction = mappings.value_to_name('body_yaw', body_yaw)
        head_tilt = mappings.value_to_name('pitch', pitch)
        head_roll = mappings.value_to_name('roll', roll)
        antennas_desc = mappings.value_to_name('antennas', antennas)
        
        return {
            "head_direction": head_direction,
            "head_tilt": head_tilt,
            "head_roll": head_roll,
            "antennas": antennas_desc,
            "body_direction": body_direction
        }
    
    def _degrees_to_compass(self, degrees: float) -> str:
        """
        Convert compass angle in degrees to nearest cardinal/intercardinal direction.
        Delegates to mappings module for consistency.
        
        Args:
            degrees: Compass angle in degrees (0=North, 90=West, -90=East)
        
        Returns:
            Compass direction string (e.g., "North", "North East", "East")
        """
        return mappings.degrees_to_compass(degrees)
            
    def move_smoothly_to(self, duration=10.0, roll=None, pitch=None, yaw=None, antennas=None, body_yaw=None):
        """
        Move the robot smoothly to a single position.
        
        Parameters default to None, which means maintain current position (constant, no oscillation).
        Only specified parameters will have smooth sinusoidal movement applied.
        
        Supports compass directions for yaw and body_yaw (e.g., "North", "East", "West").
        """
        def smooth_movement(t, target_angle, cycle_duration=2.0):
            """
            Smooth oscillating movement with constant speed.
            
            Longer duration = more repetitions, not slower movement.
            cycle_duration controls how fast one oscillation is.
            """
            # Repeat the motion: t loops within each cycle
            t_in_cycle = t % cycle_duration
            
            # Cosine ease-in-out within each cycle
            ease = (1.0 - np.cos(np.pi * t_in_cycle / cycle_duration)) / 2.0
            position_deg = target_angle * ease
            return round(np.deg2rad(position_deg), 4)

        # Get current state
        curr_roll, curr_pitch, curr_yaw, curr_antennas, curr_body_yaw = self.get_current_state()
        logger.info(f"Starting move_smoothly_to: roll={curr_roll:.1f}, pitch={curr_pitch:.1f}, yaw={curr_yaw:.1f}, antennas={curr_antennas}, body_yaw={curr_body_yaw:.1f}")
        
        # Parse compass directions if provided as strings
        if isinstance(yaw, str):
            yaw = self.parse_compass_direction(yaw)
            logger.info(f"Parsed yaw compass direction to {yaw:.1f}°")
        
        if isinstance(body_yaw, str):
            body_yaw = self.parse_compass_direction(body_yaw)
            logger.info(f"Parsed body_yaw compass direction to {body_yaw:.1f}°")
        
        # Parse duration if provided as string (defensive handling)
        if isinstance(duration, str):
            duration = mappings.name_to_value('duration', duration)
            logger.info(f"Parsed duration name to {duration}s")
            
        # Determine which parameters to animate vs keep constant
        # For None parameters, we use current values and mark them as constant
        animate_roll = roll is not None
        animate_pitch = pitch is not None
        animate_yaw = yaw is not None
        animate_antennas = antennas is not None
        animate_body_yaw = body_yaw is not None
        
        # Set target values
        target_roll = roll if roll is not None else curr_roll
        target_pitch = pitch if pitch is not None else curr_pitch
        target_yaw = yaw if yaw is not None else curr_yaw
        target_antennas = antennas if antennas is not None else curr_antennas
        target_body_yaw = body_yaw if body_yaw is not None else curr_body_yaw
        
        logger.info(f"Moving robot smoothly to: roll={roll}, pitch={pitch}, yaw={yaw}, antennas={antennas}, body_yaw={body_yaw}")  
        start_time = time.time()
        t = time.time()
        while t - start_time < duration:
            tick_in_time = t - start_time
            
            # Apply smooth movement only to animated parameters, keep others constant
            if animate_body_yaw:
                body_yaw_t = smooth_movement(tick_in_time, target_body_yaw)
            else:
                body_yaw_t = np.deg2rad(curr_body_yaw)
            
            if animate_antennas:
                antennas_t = [smooth_movement(tick_in_time, target_antennas[0]), 
                             smooth_movement(tick_in_time, target_antennas[1])]
            else:
                antennas_t = [np.deg2rad(curr_antennas[0]), np.deg2rad(curr_antennas[1])]
            
            if animate_pitch:
                pitch_t = smooth_movement(tick_in_time, target_pitch)
            else:
                pitch_t = np.deg2rad(curr_pitch)
            
            if animate_roll:
                roll_t = smooth_movement(tick_in_time, target_roll)
            else:
                roll_t = np.deg2rad(curr_roll)
            
            if animate_yaw:
                yaw_t = smooth_movement(tick_in_time, target_yaw)
            else:
                yaw_t = np.deg2rad(curr_yaw)

            (safe_roll, safe_pitch, safe_yaw, safe_antennas, safe_body_yaw) = self.apply_safety_to_movement(roll_t, pitch_t, yaw_t, antennas=antennas_t, body_yaw=body_yaw_t)

            # FIX: Update tracked body_yaw with the ACTUAL safe value used (at the end of animation)
            if tick_in_time >= duration - 0.01:  # Near end of movement
                self._current_body_yaw = np.degrees(safe_body_yaw)

            head_pose = create_head_pose(
                roll=safe_roll,
                pitch=safe_pitch,
                yaw=safe_yaw,
                degrees=False,
                mm=False,
            )
            self.mini.set_target(head=head_pose, antennas=safe_antennas, body_yaw=safe_body_yaw)
            t = time.time()
        
        # Log final state
        final_roll, final_pitch, final_yaw, final_antennas, final_body_yaw = self.get_current_state()
        logger.info(f"Finished move_smoothly_to: roll={final_roll:.1f}, pitch={final_pitch:.1f}, yaw={final_yaw:.1f}, antennas={final_antennas}, body_yaw={final_body_yaw:.1f}")

    def apply_safety_to_movement(self, roll, pitch, yaw, antennas, body_yaw):
        """
        Apply safety limits to robot movements using the SafetyManager.
        
        Delegates to external safety module for head-priority collision avoidance.
        The head is treated as "self" and the body adjusts to accommodate head movements.
        
        Args:
            roll, pitch, yaw: Head angles in radians
            antennas: Antenna positions in radians
            body_yaw: Body yaw angle in radians
            
        Returns:
            Tuple of (safe_roll, safe_pitch, safe_yaw, safe_antennas, safe_body_yaw)
        """
        # Get current state
        current_roll, current_pitch, current_yaw, current_antennas, current_body_yaw = self.get_current_state()
        
        # Convert to degrees for SafetyManager
        current_state_deg = (
            current_roll,
            current_pitch, 
            current_yaw,
            current_body_yaw
        )
        
        target_state_deg = (
            np.degrees(roll),
            np.degrees(pitch),
            np.degrees(yaw),
            np.degrees(body_yaw)
        )
        
        # Validate movement with safety manager
        safe_roll_deg, safe_pitch_deg, safe_yaw_deg, safe_body_yaw_deg = self.safety_manager.validate_movement(
            current_state=current_state_deg,
            target_state=target_state_deg
        )
        
        # Convert back to radians
        safe_roll = np.deg2rad(safe_roll_deg)
        safe_pitch = np.deg2rad(safe_pitch_deg)
        safe_yaw = np.deg2rad(safe_yaw_deg)
        safe_body_yaw = np.deg2rad(safe_body_yaw_deg)
        
        # Antennas pass through unchanged
        safe_antennas = antennas
        
        return (safe_roll, safe_pitch, safe_yaw, safe_antennas, safe_body_yaw)
    
    def update_safety_config(self, **config_params):
        """
        Update safety configuration parameters at runtime.
        
        Allows fine-tuning of collision zones, margins, and limits.
        
        Args:
            **config_params: Safety config parameters to update
                (e.g., SAFE_MARGINS=10, BODY_RETREAT_ANGLE=15)
        
        Example:
            controller.update_safety_config(
                SAFE_MARGINS=10.0,
                BODY_RETREAT_ANGLE=15.0,
                HEAD_ROLL_LIMIT=30.0
            )
        """
        for param, value in config_params.items():
            if hasattr(self.safety_config, param):
                setattr(self.safety_config, param, value)
                logger.info(f"Updated safety config: {param}={value}")
            else:
                logger.warning(f"Unknown safety config parameter: {param}")
        
        logger.info(f"Safety configuration updated with {len(config_params)} parameters")

    def turn_off_smoothly(self):
        """
        Smoothly move the robot to a neutral position and then turn off compliance.
        
        """
        logger.info(f"Reachy mini is going to sleep...")
        if (self.reachy_is_awake):
            self.reachy_is_awake = False
            # Move to neutral position (0, 0, 0)
            self.mini.goto_sleep()


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
                self.turn_off_smoothly()
                logger.info("ReachyMini cleaned up successfully")
            except Exception as e:
                logger.error(f"Error cleaning up ReachyMini: {e}")
