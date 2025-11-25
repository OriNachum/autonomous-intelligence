#!/usr/bin/env python3
"""
Safety Manager Module

This module provides safety management for Reachy robot movements with
head-priority collision avoidance. The head is treated as "self" and
the body will adjust to accommodate head movements.

Key features:
- Configurable safety limits and collision zones
- Head-priority collision resolution
- Dynamic body adjustment based on head position
"""

import logging
import numpy as np
from typing import Tuple, Dict, Optional
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


@dataclass
class SafetyConfig:
    """Configuration for safety limits and collision zones."""
    
    # Basic angle limits (in degrees)
    HEAD_YAW_LIMIT: float = 40.0
    HEAD_PITCH_LIMIT: float = 20.0
    HEAD_ROLL_LIMIT: float = 25.0
    BODY_YAW_LIMIT: float = 25.0
    MAX_YAW_DIFFERENCE: float = 30.0
    
    # Collision avoidance parameters
    SAFE_MARGINS: float = 5.0  # Buffer zone in degrees
    BODY_RETREAT_ANGLE: float = 10.0  # How much body retreats when head tilts
    
    # Collision zones: define dangerous head-body configurations
    # Format: {'zone_name': {'roll_min': float, 'roll_max': float, 
    #                        'pitch_min': float, 'pitch_max': float,
    #                        'body_yaw_conflict_min': float, 'body_yaw_conflict_max': float}}
    COLLISION_ZONES: Dict = field(default_factory=lambda: {
        'left_tilt_with_left_body': {
            'roll_min': 10.0,  # Head tilted left
            'roll_max': 30.0,
            'pitch_min': -20.0,
            'pitch_max': 20.0,
            'body_yaw_conflict_min': 5.0,  # Body also rotated left
            'body_yaw_conflict_max': 25.0,
        },
        'right_tilt_with_right_body': {
            'roll_min': -30.0,  # Head tilted right
            'roll_max': -10.0,
            'pitch_min': -20.0,
            'pitch_max': 20.0,
            'body_yaw_conflict_min': -25.0,  # Body also rotated right
            'body_yaw_conflict_max': -5.0,
        },
    })


class SafetyManager:
    """
    Safety manager for robot movements with head-priority collision avoidance.
    
    The head is treated as the "self" and has priority. The body will adjust
    to accommodate head movements and avoid collisions.
    """
    
    def __init__(self, config: Optional[SafetyConfig] = None):
        """
        Initialize safety manager.
        
        Args:
            config: Safety configuration. Uses default if None.
        """
        self.config = config or SafetyConfig()
        logger.info("SafetyManager initialized with config: "
                   f"HEAD_YAW={self.config.HEAD_YAW_LIMIT}°, "
                   f"BODY_YAW={self.config.BODY_YAW_LIMIT}°, "
                   f"SAFE_MARGINS={self.config.SAFE_MARGINS}°")
    
    def validate_movement(
        self,
        current_state: Tuple[float, float, float, float],
        target_state: Tuple[float, float, float, float]
    ) -> Tuple[float, float, float, float]:
        """
        Validate and adjust movement to ensure safety with head priority.
        
        Args:
            current_state: Current (roll, pitch, yaw, body_yaw) in degrees
            target_state: Target (roll, pitch, yaw, body_yaw) in degrees
            
        Returns:
            Safe (roll, pitch, yaw, body_yaw) in degrees
        """
        current_roll, current_pitch, current_yaw, current_body_yaw = current_state
        target_roll, target_pitch, target_yaw, target_body_yaw = target_state
        
        # Convert to radians for calculations
        target_roll_rad = np.deg2rad(target_roll)
        target_pitch_rad = np.deg2rad(target_pitch)
        target_yaw_rad = np.deg2rad(target_yaw)
        target_body_yaw_rad = np.deg2rad(target_body_yaw)
        current_body_yaw_rad = np.deg2rad(current_body_yaw)
        
        # Step 1: Apply basic angle limits
        safe_roll_rad, safe_pitch_rad, safe_yaw_rad, safe_body_yaw_rad = self._apply_basic_limits(
            target_roll_rad, target_pitch_rad, target_yaw_rad, target_body_yaw_rad
        )
        
        # Step 2: Apply head-priority collision resolution
        safe_body_yaw_rad = self._resolve_head_body_collision(
            current_state=(current_roll, current_pitch, current_yaw, current_body_yaw),
            target_head=(np.degrees(safe_roll_rad), np.degrees(safe_pitch_rad), np.degrees(safe_yaw_rad)),
            target_body_yaw=np.degrees(safe_body_yaw_rad)
        )
        safe_body_yaw_rad = np.deg2rad(safe_body_yaw_rad)
        
        # Step 3: Ensure yaw difference constraint
        safe_yaw_rad, safe_body_yaw_rad = self._enforce_yaw_difference(
            safe_yaw_rad, safe_body_yaw_rad
        )
        
        # Convert back to degrees
        safe_roll = np.degrees(safe_roll_rad)
        safe_pitch = np.degrees(safe_pitch_rad)
        safe_yaw = np.degrees(safe_yaw_rad)
        safe_body_yaw = np.degrees(safe_body_yaw_rad)
        
        # Log if adjustments were made
        if (abs(safe_roll - target_roll) > 0.1 or 
            abs(safe_pitch - target_pitch) > 0.1 or
            abs(safe_yaw - target_yaw) > 0.1 or
            abs(safe_body_yaw - target_body_yaw) > 0.1):
            logger.info(f"Safety adjustment applied: "
                       f"roll {target_roll:.1f}°→{safe_roll:.1f}°, "
                       f"pitch {target_pitch:.1f}°→{safe_pitch:.1f}°, "
                       f"yaw {target_yaw:.1f}°→{safe_yaw:.1f}°, "
                       f"body_yaw {target_body_yaw:.1f}°→{safe_body_yaw:.1f}°")
        
        return (safe_roll, safe_pitch, safe_yaw, safe_body_yaw)
    
    def _apply_basic_limits(
        self,
        roll: float,
        pitch: float,
        yaw: float,
        body_yaw: float
    ) -> Tuple[float, float, float, float]:
        """
        Apply basic angle limits without collision consideration.
        
        Args:
            roll, pitch, yaw, body_yaw: Target angles in radians
            
        Returns:
            Clamped angles in radians
        """
        HEAD_YAW_LIMIT_RAD = np.deg2rad(self.config.HEAD_YAW_LIMIT)
        HEAD_PITCH_LIMIT_RAD = np.deg2rad(self.config.HEAD_PITCH_LIMIT)
        HEAD_ROLL_LIMIT_RAD = np.deg2rad(self.config.HEAD_ROLL_LIMIT)
        BODY_YAW_LIMIT_RAD = np.deg2rad(self.config.BODY_YAW_LIMIT)
        
        safe_roll = np.clip(roll, -HEAD_ROLL_LIMIT_RAD, HEAD_ROLL_LIMIT_RAD)
        safe_pitch = np.clip(pitch, -HEAD_PITCH_LIMIT_RAD, HEAD_PITCH_LIMIT_RAD)
        safe_yaw = np.clip(yaw, -HEAD_YAW_LIMIT_RAD, HEAD_YAW_LIMIT_RAD)
        safe_body_yaw = np.clip(body_yaw, -BODY_YAW_LIMIT_RAD, BODY_YAW_LIMIT_RAD)
        
        return (safe_roll, safe_pitch, safe_yaw, safe_body_yaw)
    
    def _resolve_head_body_collision(
        self,
        current_state: Tuple[float, float, float, float],
        target_head: Tuple[float, float, float],
        target_body_yaw: float
    ) -> float:
        """
        Resolve collisions with head having priority (HEAD IS SELF).
        
        Three scenarios:
        1. Head tilting while body stationary → Move body to safe zone
        2. Head tilted, body trying to move → Constrain body movement
        3. Body at extreme angle, head tilting → Body retreats toward center
        
        Args:
            current_state: Current (roll, pitch, yaw, body_yaw) in degrees
            target_head: Target (roll, pitch, yaw) in degrees
            target_body_yaw: Target body_yaw in degrees
            
        Returns:
            Adjusted body_yaw in degrees
        """
        current_roll, current_pitch, current_yaw, current_body_yaw = current_state
        target_roll, target_pitch, target_yaw = target_head
        
        # Check if head is tilting significantly
        head_is_tilted = abs(target_roll) > self.config.SAFE_MARGINS
        
        # Scenario 1 & 3: Head tilting forces body to move
        if head_is_tilted:
            # Check if in collision zone
            if self._check_collision_zone(target_roll, target_pitch, target_yaw, target_body_yaw):
                logger.info(f"HEAD PRIORITY: Head tilt {target_roll:.1f}° detected in collision zone")
                
                # Calculate safe body position (move away from head tilt)
                adjusted_body_yaw = self._calculate_safe_body_position(
                    target_roll, target_pitch, target_yaw, target_body_yaw
                )
                
                logger.info(f"HEAD PRIORITY: Body adjusted from {target_body_yaw:.1f}° to {adjusted_body_yaw:.1f}° "
                           f"to accommodate head tilt")
                return adjusted_body_yaw
            
            # Scenario 2: Head tilted, constrain body movement
            max_safe_body_yaw = self._calculate_max_safe_body_yaw(target_roll, target_pitch, target_yaw)
            
            if abs(target_body_yaw) > max_safe_body_yaw:
                adjusted_body_yaw = np.sign(target_body_yaw) * max_safe_body_yaw
                logger.info(f"HEAD PRIORITY: Body movement constrained from {target_body_yaw:.1f}° "
                           f"to {adjusted_body_yaw:.1f}° due to head tilt {target_roll:.1f}°")
                return adjusted_body_yaw
        
        return target_body_yaw
    
    def _check_collision_zone(
        self,
        roll: float,
        pitch: float,
        yaw: float,
        body_yaw: float
    ) -> bool:
        """
        Check if current configuration is in a collision zone.
        
        Args:
            roll, pitch, yaw, body_yaw: Angles in degrees
            
        Returns:
            True if in collision zone
        """
        for zone_name, zone in self.config.COLLISION_ZONES.items():
            roll_in_zone = zone['roll_min'] <= roll <= zone['roll_max']
            pitch_in_zone = zone['pitch_min'] <= pitch <= zone['pitch_max']
            body_yaw_in_zone = zone['body_yaw_conflict_min'] <= body_yaw <= zone['body_yaw_conflict_max']
            
            if roll_in_zone and pitch_in_zone and body_yaw_in_zone:
                logger.debug(f"Collision zone '{zone_name}' detected: "
                           f"roll={roll:.1f}°, pitch={pitch:.1f}°, body_yaw={body_yaw:.1f}°")
                return True
        
        return False
    
    def _calculate_safe_body_position(
        self,
        head_roll: float,
        head_pitch: float,
        head_yaw: float,
        current_body_yaw: float
    ) -> float:
        """
        Calculate safe body position when head is tilting.
        
        The body should move AWAY from the tilt direction to create space.
        
        Args:
            head_roll: Head roll angle in degrees (positive = tilt left)
            head_pitch: Head pitch in degrees
            head_yaw: Head yaw in degrees
            current_body_yaw: Current body yaw in degrees
            
        Returns:
            Safe body_yaw in degrees
        """
        # If head tilts left (positive roll), body should move right (negative yaw)
        # If head tilts right (negative roll), body should move left (positive yaw)
        retreat_direction = -np.sign(head_roll)
        safe_body_yaw = retreat_direction * self.config.BODY_RETREAT_ANGLE
        
        # Clamp to body limits
        BODY_YAW_LIMIT = self.config.BODY_YAW_LIMIT
        safe_body_yaw = np.clip(safe_body_yaw, -BODY_YAW_LIMIT, BODY_YAW_LIMIT)
        
        return safe_body_yaw
    
    def _calculate_max_safe_body_yaw(
        self,
        head_roll: float,
        head_pitch: float,
        head_yaw: float
    ) -> float:
        """
        Calculate maximum safe body yaw when head is tilted.
        
        When head is tilted, body movement range is restricted.
        
        Args:
            head_roll: Head roll angle in degrees
            head_pitch: Head pitch in degrees
            head_yaw: Head yaw in degrees
            
        Returns:
            Maximum safe absolute body_yaw in degrees
        """
        # The more the head tilts, the more we restrict body movement
        tilt_factor = abs(head_roll) / self.config.HEAD_ROLL_LIMIT
        
        # At maximum tilt, reduce body yaw range by retreat angle
        max_safe_yaw = self.config.BODY_YAW_LIMIT - (tilt_factor * self.config.BODY_RETREAT_ANGLE)
        
        # Ensure minimum range
        max_safe_yaw = max(max_safe_yaw, 5.0)
        
        return max_safe_yaw
    
    def _enforce_yaw_difference(
        self,
        yaw: float,
        body_yaw: float
    ) -> Tuple[float, float]:
        """
        Ensure difference between head yaw and body yaw doesn't exceed limit.
        
        Args:
            yaw: Head yaw in radians
            body_yaw: Body yaw in radians
            
        Returns:
            Adjusted (yaw, body_yaw) in radians
        """
        MAX_YAW_DIFFERENCE_RAD = np.deg2rad(self.config.MAX_YAW_DIFFERENCE)
        yaw_difference = abs(yaw - body_yaw)
        
        if yaw_difference > MAX_YAW_DIFFERENCE_RAD:
            # Bring them closer by adjusting both proportionally
            excess = yaw_difference - MAX_YAW_DIFFERENCE_RAD
            
            if yaw > body_yaw:
                yaw -= excess / 2
                body_yaw += excess / 2
            else:
                yaw += excess / 2
                body_yaw -= excess / 2
            
            logger.debug(f"Yaw difference adjusted: "
                        f"diff={np.degrees(yaw_difference):.1f}° "
                        f"→ {np.degrees(abs(yaw - body_yaw)):.1f}°")
        
        return (yaw, body_yaw)
