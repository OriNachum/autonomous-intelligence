#!/usr/bin/env python3
"""
Robot Pose Data Structure

This module defines the RobotPose dataclass for representing the complete
state of the robot (head orientation and antenna positions).
"""

import numpy as np
from dataclasses import dataclass
from typing import Tuple, Optional
import logging

logger = logging.getLogger(__name__)


@dataclass
class RobotPose:
    """
    Complete robot pose representation.
    
    All angles are stored in degrees for human readability.
    """
    roll: float = 0.0           # Head roll in degrees
    pitch: float = 0.0          # Head pitch in degrees
    yaw: float = 0.0            # Head yaw in degrees
    antennas: Tuple[float, float] = (0.0, 0.0)  # Left and right antenna positions in degrees
    body_yaw: float = 0.0       # Body yaw in degrees
    
    @classmethod
    def from_radians(cls, roll: float, pitch: float, yaw: float, 
                     antennas: Tuple[float, float], body_yaw: float) -> 'RobotPose':
        """
        Create a RobotPose from radian values.
        
        Args:
            roll, pitch, yaw: Head angles in radians
            antennas: Antenna positions in radians (left, right)
            body_yaw: Body yaw in radians
            
        Returns:
            RobotPose with values converted to degrees
        """
        return cls(
            roll=np.degrees(roll),
            pitch=np.degrees(pitch),
            yaw=np.degrees(yaw),
            antennas=(np.degrees(antennas[0]), np.degrees(antennas[1])),
            body_yaw=np.degrees(body_yaw)
        )
    
    def to_radians(self) -> Tuple[float, float, float, Tuple[float, float], float]:
        """
        Convert pose to radians.
        
        Returns:
            Tuple of (roll, pitch, yaw, antennas, body_yaw) all in radians
        """
        return (
            np.radians(self.roll),
            np.radians(self.pitch),
            np.radians(self.yaw),
            (np.radians(self.antennas[0]), np.radians(self.antennas[1])),
            np.radians(self.body_yaw)
        )
    
    @classmethod
    def from_current_state(cls, reachy_controller) -> 'RobotPose':
        """
        Capture the current robot state from ReachyController.
        
        Args:
            reachy_controller: ReachyController instance
            
        Returns:
            RobotPose representing current state
        """
        roll, pitch, yaw, antennas, body_yaw = reachy_controller.get_current_state()
        return cls(
            roll=roll,
            pitch=pitch,
            yaw=yaw,
            antennas=(antennas[0], antennas[1]),
            body_yaw=body_yaw
        )
    
    def blend(self, other: 'RobotPose', alpha: float) -> 'RobotPose':
        """
        Linearly interpolate between this pose and another.
        
        Args:
            other: Target pose
            alpha: Blend factor (0.0 = this pose, 1.0 = other pose)
            
        Returns:
            Blended pose
        """
        alpha = np.clip(alpha, 0.0, 1.0)
        
        return RobotPose(
            roll=self.roll * (1 - alpha) + other.roll * alpha,
            pitch=self.pitch * (1 - alpha) + other.pitch * alpha,
            yaw=self.yaw * (1 - alpha) + other.yaw * alpha,
            antennas=(
                self.antennas[0] * (1 - alpha) + other.antennas[0] * alpha,
                self.antennas[1] * (1 - alpha) + other.antennas[1] * alpha
            ),
            body_yaw=self.body_yaw * (1 - alpha) + other.body_yaw * alpha
        )
    
    def copy(self) -> 'RobotPose':
        """Create an independent copy of this pose."""
        return RobotPose(
            roll=self.roll,
            pitch=self.pitch,
            yaw=self.yaw,
            antennas=(self.antennas[0], self.antennas[1]),
            body_yaw=self.body_yaw
        )
    
    def __str__(self) -> str:
        """String representation for debugging."""
        return (f"RobotPose(roll={self.roll:.1f}°, pitch={self.pitch:.1f}°, "
                f"yaw={self.yaw:.1f}°, antennas=({self.antennas[0]:.1f}°, {self.antennas[1]:.1f}°), "
                f"body_yaw={self.body_yaw:.1f}°)")
