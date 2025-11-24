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

logger = logging.getLogger(__name__)


class ReachyController:
    """Direction of Audio Detector using ReachyMini"""
    
    # Natural language mappings for robot movements
    NATURAL_MAPPINGS = {
        # Pitch (nodding): up/down movements
        'pitch': {
            'up': 15.0,
            'down': -15.0,
            'slight up': 8.0,
            'slight down': -8.0,
        },
        # Roll (tilting): side tilt movements
        'roll': {
            'left': 20.0,
            'right': -20.0,
            'slight left': 10.0,
            'slight right': -10.0,
        },
        # Antennas: expressive movements
        'antennas': {
            'wiggle': [180.0, 180.0],
            'up': [30.0, 30.0],
            'down': [-30.0, -30.0],
            'curious': [45.0, 45.0],
            'neutral': [0.0, 0.0],
        }
    }
    
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
            self.reachy_is_awake = True
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
        
        # Track body yaw state (not directly readable from ReachyMini)
        self._current_body_yaw = 0.0
        
        logger.info(f"DOA Detector initialized with smoothing_alpha={smoothing_alpha}")
    
    def parse_compass_direction(self, direction_str: str) -> float:
        """
        Parse compass direction string and convert to Reachy yaw angle in degrees.
        
        Uses vector addition to handle arbitrary compass strings like "North East".
        Reachy's yaw is limited to ±45°, where:
        - North (0°) = forward = 0° in Reachy
        - East (90°) = right = -45° in Reachy (max right)
        - West (-90°) = left = +45° in Reachy (max left)
        
        Formula: reachy_yaw = -1 * (compass_angle / 2)
        
        Args:
            direction_str: Compass direction (e.g., "North", "East", "North East")
        
        Returns:
            Yaw angle in degrees for Reachy, clamped to ±45°
        """
        # Define unit vectors for cardinal directions
        CARDINAL_VECTORS = {
            'north': (0, 1),
            'south': (0, -1),
            'west': (1, 0),
            'east': (-1, 0),
        }
        
        # Normalize input: lowercase and remove extra spaces
        direction_str = direction_str.lower().strip()
        
        # Tokenize the input (split on spaces and common separators)
        tokens = direction_str.replace('-', ' ').replace('_', ' ').split()
        
        # Sum the vectors
        total_x, total_y = 0.0, 0.0
        
        for token in tokens:
            if token in CARDINAL_VECTORS:
                x, y = CARDINAL_VECTORS[token]
                total_x += x
                total_y += y
        
        # If no valid tokens found, default to North (forward)
        if total_x == 0 and total_y == 0:
            logger.warning(f"No valid compass direction in '{direction_str}', defaulting to North (0°)")
            return 0.0
        
        # Calculate the angle of the resulting vector relative to North
        # atan2 gives angle from East (positive x-axis), we need from North (positive y-axis)
        compass_angle_rad = np.arctan2(total_x, total_y)  # Note: swapped x and y for North=0
        compass_angle_deg = np.degrees(compass_angle_rad)
        
        # Map compass angle to Reachy yaw
        # Compass: East=90°, West=-90° (or 270°)
        # Reachy: Max Right=-45°, Max Left=+45°
        # Formula: reachy_yaw = -1 * (compass_angle / 2)
        reachy_yaw = -1.0 * (compass_angle_deg / 2.0)
        
        # Clamp to safety limits (±45°)
        MAX_YAW = 45.0
        reachy_yaw = np.clip(reachy_yaw, -MAX_YAW, MAX_YAW)
        
        logger.debug(f"Parsed compass direction '{direction_str}': compass_angle={compass_angle_deg:.1f}°, "
                    f"reachy_yaw={reachy_yaw:.1f}°")
        
        return float(reachy_yaw)
    
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
    
    def _get_current_state(self) -> Tuple[float, float, float, list, float]:
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
        Get current robot state expressed in natural language (compass directions).
        
        Returns:
            Dictionary with natural language descriptions:
            {
                "head_direction": "East" or "North" or "West" etc.,
                "head_tilt": "looking up" or "looking down" or "level",
                "head_roll": "tilted left" or "tilted right" or "upright",
                "antennas": "wiggling" or "neutral" or "up",
                "body_direction": "East" or "North" or "West" etc.
            }
        """
        roll, pitch, yaw, antennas, body_yaw = self._get_current_state()
        
        # Convert yaw to compass direction
        # Inverse of parse_compass_direction: reachy_yaw = -1 * (compass_angle / 2)
        # So: compass_angle = -2 * reachy_yaw
        compass_angle_yaw = -2.0 * yaw
        head_direction = self._degrees_to_compass(compass_angle_yaw)
        
        # Convert body_yaw to compass direction
        compass_angle_body = -2.0 * body_yaw
        body_direction = self._degrees_to_compass(compass_angle_body)
        
        # Pitch to natural language
        if pitch > 5.0:
            head_tilt = "looking up"
        elif pitch < -5.0:
            head_tilt = "looking down"
        else:
            head_tilt = "level"
        
        # Roll to natural language
        if roll > 5.0:
            head_roll = "tilted left"
        elif roll < -5.0:
            head_roll = "tilted right"
        else:
            head_roll = "upright"
        
        # Antennas (simple classification)
        avg_antenna = sum(antennas) / 2.0
        if abs(avg_antenna) < 5.0:
            antennas_desc = "neutral"
        elif avg_antenna > 20.0:
            antennas_desc = "up"
        elif avg_antenna < -20.0:
            antennas_desc = "down"
        else:
            antennas_desc = "neutral"
        
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
        
        Args:
            degrees: Compass angle in degrees (0=North, 90=East, -90=West)
        
        Returns:
            Compass direction string (e.g., "North", "North East", "East")
        """
        # Normalize to [0, 360)
        degrees = degrees % 360.0
        
        # Quantize to 8 directions (N, NE, E, SE, S, SW, W, NW)
        # Each direction spans 45°
        directions = [
            "North",      # 337.5-22.5 (wraps around 0)
            "North West", # 22.5-67.5
            "West",       # 67.5-112.5
            "South West", # 112.5-157.5
            "South",      # 157.5-202.5
            "South East", # 202.5-247.5
            "East",       # 247.5-292.5
            "North East"  # 292.5-337.5
        ]
        
        # Convert to index (0-7)
        # Add 22.5 to shift boundaries, divide by 45 to get direction
        index = int((degrees + 22.5) / 45.0) % 8
        
        return directions[index]
    
    def move_to(self, duration=10.0, method=InterpolationTechnique.MIN_JERK, roll=None, pitch=None, yaw=None, antennas=None, body_yaw=None):
        """
        Move the robot to a target head pose and/or antennas position and/or body direction.
        
        Parameters default to None, which means maintain current position.
        Only specified parameters will be changed.
        
        Supports compass directions for yaw and body_yaw (e.g., "North", "East", "West").
        """
        # Get current state
        curr_roll, curr_pitch, curr_yaw, curr_antennas, curr_body_yaw = self._get_current_state()
        logger.info(f"Starting move_to: roll={curr_roll:.1f}, pitch={curr_pitch:.1f}, yaw={curr_yaw:.1f}, antennas={curr_antennas}, body_yaw={curr_body_yaw:.1f}")
        
        # Parse compass directions if provided as strings
        if isinstance(yaw, str):
            yaw = self.parse_compass_direction(yaw)
            logger.info(f"Parsed yaw compass direction to {yaw:.1f}°")
        
        if isinstance(body_yaw, str):
            body_yaw = self.parse_compass_direction(body_yaw)
            logger.info(f"Parsed body_yaw compass direction to {body_yaw:.1f}°")
        
        # Resolve None values to current state
        target_roll = roll if roll is not None else curr_roll
        target_pitch = pitch if pitch is not None else curr_pitch
        target_yaw = yaw if yaw is not None else curr_yaw
        target_antennas = antennas if antennas is not None else curr_antennas
        target_body_yaw = body_yaw if body_yaw is not None else curr_body_yaw
        
        # Apply safety and execute movement
        (safe_roll, safe_pitch, safe_yaw, safe_antennas, safe_body_yaw) = self.apply_safety_to_movement(
            np.deg2rad(target_roll),
            np.deg2rad(target_pitch),
            np.deg2rad(target_yaw), 
            [np.deg2rad(target_antennas[0]), np.deg2rad(target_antennas[1])], 
            np.deg2rad(target_body_yaw)
        )
        
        # FIX: Update tracked body_yaw with the ACTUAL safe value used
        self._current_body_yaw = np.degrees(safe_body_yaw)
        
        self.mini.goto_target(create_head_pose(roll=safe_roll, pitch=safe_pitch, yaw=safe_yaw), antennas=safe_antennas, duration=duration, method=method, body_yaw=safe_body_yaw)
        
        # Log final state
        final_roll, final_pitch, final_yaw, final_antennas, final_body_yaw = self._get_current_state()
        logger.info(f"Finished move_to: roll={final_roll:.1f}, pitch={final_pitch:.1f}, yaw={final_yaw:.1f}, antennas={final_antennas}, body_yaw={final_body_yaw:.1f}")
    
    def move_cyclically(self, duration=10.0, repetitions=1, roll=None, pitch=None, yaw=None, antennas=None, body_yaw=None):
        """
        A cyclical movement.
        
        Parameters default to None, which means maintain current position.
        Only specified parameters will have cyclical movement applied.
        
        Supports compass directions for yaw and body_yaw (e.g., "North", "East", "West").
        """
        # Parse compass directions if provided as strings
        if isinstance(yaw, str):
            yaw = self.parse_compass_direction(yaw)
            logger.info(f"Parsed yaw compass direction to {yaw:.1f}°")
        
        if isinstance(body_yaw, str):
            body_yaw = self.parse_compass_direction(body_yaw)
            logger.info(f"Parsed body_yaw compass direction to {body_yaw:.1f}°")
        
        # Log initial state
        curr_roll, curr_pitch, curr_yaw, curr_antennas, curr_body_yaw = self._get_current_state()
        logger.info(f"Starting move_cyclically: roll={curr_roll:.1f}, pitch={curr_pitch:.1f}, yaw={curr_yaw:.1f}, antennas={curr_antennas}, body_yaw={curr_body_yaw:.1f}")

        for _ in range(1):
            t = time.time()
            # get state
            original_roll, original_pitch, original_yaw, original_antennas, original_body_yaw = self._get_current_state()
            self.move_smoothly_to(duration=duration, roll=roll, pitch=pitch, yaw=yaw, antennas=antennas, body_yaw=body_yaw)
            # Use state from previous move
            self.move_smoothly_to(duration=duration, roll=original_roll, pitch=original_pitch, yaw=original_yaw, antennas=original_antennas, body_yaw=original_body_yaw)

        # Log final state
        final_roll, final_pitch, final_yaw, final_antennas, final_body_yaw = self._get_current_state()
        logger.info(f"Finished move_cyclically: roll={final_roll:.1f}, pitch={final_pitch:.1f}, yaw={final_yaw:.1f}, antennas={final_antennas}, body_yaw={final_body_yaw:.1f}")

        
    def move_smoothly_to(self, duration=10.0, roll=None, pitch=None, yaw=None, antennas=None, body_yaw=None):
        """
        Move the robot smoothly to a single position.
        
        Parameters default to None, which means maintain current position (constant, no oscillation).
        Only specified parameters will have smooth sinusoidal movement applied.
        
        Supports compass directions for yaw and body_yaw (e.g., "North", "East", "West").
        """
        def smooth_movement(t, max_angle):
            phase = np.pi / 2 * t / duration
            smooth_position = np.deg2rad(max_angle * np.sin(phase))
            # Apply 2 decimal points precision
            smooth_position = round(smooth_position, 2)
            return smooth_position
        
        # Get current state
        curr_roll, curr_pitch, curr_yaw, curr_antennas, curr_body_yaw = self._get_current_state()
        logger.info(f"Starting move_smoothly_to: roll={curr_roll:.1f}, pitch={curr_pitch:.1f}, yaw={curr_yaw:.1f}, antennas={curr_antennas}, body_yaw={curr_body_yaw:.1f}")
        
        # Parse compass directions if provided as strings
        if isinstance(yaw, str):
            yaw = self.parse_compass_direction(yaw)
            logger.info(f"Parsed yaw compass direction to {yaw:.1f}°")
        
        if isinstance(body_yaw, str):
            body_yaw = self.parse_compass_direction(body_yaw)
            logger.info(f"Parsed body_yaw compass direction to {body_yaw:.1f}°")
        
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
        final_roll, final_pitch, final_yaw, final_antennas, final_body_yaw = self._get_current_state()
        logger.info(f"Finished move_smoothly_to: roll={final_roll:.1f}, pitch={final_pitch:.1f}, yaw={final_yaw:.1f}, antennas={final_antennas}, body_yaw={final_body_yaw:.1f}")

    def apply_safety_to_movement(self, roll, pitch, yaw, antennas, body_yaw):
        """
        Apply safety limits to robot movements.
        
        - Head yaw is limited to ±40 degrees
        - Overflow beyond ±40 degrees is redirected to body_yaw
        - Body yaw is limited to ±25 degrees
        - Overflow beyond ±25 degrees is redirected to head yaw
        - Difference between yaw and body_yaw never exceeds 45 degrees
        - If they move in opposite directions and would exceed 45°, they are averaged proportionally
        - Head pitch is limited to ±20 degrees
        - Head roll is limited to ±25 degrees
        """
        HEAD_YAW_LIMIT = np.deg2rad(40.0)  # 40 degrees in radians
        HEAD_PITCH_LIMIT = np.deg2rad(20.0)  # 20 degrees in radians
        HEAD_ROLL_LIMIT = np.deg2rad(25.0)  # 25 degrees in radians
        BODY_YAW_LIMIT = np.deg2rad(25.0)  # 25 degrees in radians
        MAX_YAW_DIFFERENCE = np.deg2rad(30.0)  # 45 degrees in radians
        
        safe_antennas = antennas
        
        # Handle head roll limit
        if abs(roll) > HEAD_ROLL_LIMIT:
            safe_roll = np.sign(roll) * HEAD_ROLL_LIMIT
            logger.debug(f"Head roll limited: requested={np.degrees(roll):.1f}°, "
                        f"safe_roll={np.degrees(safe_roll):.1f}°")
        else:
            safe_roll = roll
        
        # Handle head pitch limit
        if abs(pitch) > HEAD_PITCH_LIMIT:
            safe_pitch = np.sign(pitch) * HEAD_PITCH_LIMIT
            logger.debug(f"Head pitch limited: requested={np.degrees(pitch):.1f}°, "
                        f"safe_pitch={np.degrees(safe_pitch):.1f}°")
        else:
            safe_pitch = pitch
        
        # Start with requested values
        safe_yaw = yaw
        safe_body_yaw = body_yaw
        
        # Handle head yaw overflow by redirecting to body_yaw
        if abs(yaw) > HEAD_YAW_LIMIT:
            # Calculate overflow amount
            overflow = yaw - np.sign(yaw) * HEAD_YAW_LIMIT
            safe_yaw = np.sign(yaw) * HEAD_YAW_LIMIT  # FIX: Clamp to limit
            # Add overflow to body_yaw
            safe_body_yaw = body_yaw + overflow
            
            logger.debug(f"Head yaw limited: requested={np.degrees(yaw):.1f}°, "
                        f"safe_yaw={np.degrees(safe_yaw):.1f}°, "
                        f"overflow={np.degrees(overflow):.1f}° redirected to body_yaw")
        
        # Handle body yaw overflow by redirecting to head yaw
        if abs(safe_body_yaw) > BODY_YAW_LIMIT:
            # Calculate overflow amount
            body_overflow = safe_body_yaw - np.sign(safe_body_yaw) * BODY_YAW_LIMIT
            safe_body_yaw = np.sign(safe_body_yaw) * BODY_YAW_LIMIT  # FIX: Clamp to limit
            # Add overflow to head yaw
            safe_yaw = safe_yaw + body_overflow
            
            logger.debug(f"Body yaw limited: requested={np.degrees(body_yaw):.1f}°, "
                        f"safe_body_yaw={np.degrees(safe_body_yaw):.1f}°, "
                        f"overflow={np.degrees(body_overflow):.1f}° redirected to head yaw")
        
        # Ensure difference between yaw and body_yaw never exceeds 45 degrees
        yaw_difference = abs(safe_yaw - safe_body_yaw)
        
        if yaw_difference > MAX_YAW_DIFFERENCE:
            # They are too far apart - need to bring them closer
            # Average them proportionally based on how much each contributes
            
            # Calculate the midpoint
            total_angle = safe_yaw + safe_body_yaw
            
            # Calculate how much we need to adjust
            excess = yaw_difference - MAX_YAW_DIFFERENCE
            
            # Proportionally reduce the difference
            # Move each one toward the other by half the excess
            if safe_yaw > safe_body_yaw:
                safe_yaw -= excess / 2
                safe_body_yaw += excess / 2
            else:
                safe_yaw += excess / 2
                safe_body_yaw -= excess / 2
            
            logger.debug(f"Yaw difference exceeded 45°: original_diff={np.degrees(yaw_difference):.1f}°, "
                        f"adjusted yaw={np.degrees(safe_yaw):.1f}°, "
                        f"adjusted body_yaw={np.degrees(safe_body_yaw):.1f}°, "
                        f"new_diff={np.degrees(abs(safe_yaw - safe_body_yaw)):.1f}°")

        return (safe_roll, safe_pitch, safe_yaw, safe_antennas, safe_body_yaw)

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
