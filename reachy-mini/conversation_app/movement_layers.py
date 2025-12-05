#!/usr/bin/env python3
"""
Movement Layers System

This module defines the layer-based movement system that allows compositing
different movement sources (base poses, idle animations, gestures).
"""

import time
import math
import numpy as np
import logging
from abc import ABC, abstractmethod
from typing import Optional

try:
    from .robot_pose import RobotPose
except ImportError:
    from robot_pose import RobotPose

logger = logging.getLogger(__name__)


class MovementLayer(ABC):
    """
    Abstract base class for movement layers.
    
    Each layer can contribute to the final robot pose based on time and state.
    """
    
    @abstractmethod
    def is_active(self) -> bool:
        """Check if this layer should be applied."""
        pass
    
    @abstractmethod
    def get_pose(self, current_time: float) -> Optional[RobotPose]:
        """
        Compute this layer's contribution to the robot pose.
        
        Args:
            current_time: Current time in seconds (from time.time())
            
        Returns:
            RobotPose or None if layer has no contribution
        """
        pass


class BasePoseLayer(MovementLayer):
    """
    Layer that manages the primary target position with smooth transitions.
    
    Handles smooth interpolation from current pose to target pose using
    configurable easing functions.
    """
    
    def __init__(self):
        """Initialize the base pose layer."""
        self._current_pose = RobotPose()  # Start at neutral
        self._target_pose = RobotPose()
        self._transition_start_time = None
        self._transition_duration = 0.0
        self._in_transition = False
        
        logger.info("BasePoseLayer initialized")
    
    def is_active(self) -> bool:
        """Base layer is always active."""
        return True
    
    def set_target(self, target_pose: RobotPose, duration: float = 2.0):
        """
        Set a new target pose with smooth transition.
        
        Args:
            target_pose: Desired final pose
            duration: Transition duration in seconds
        """
        # Start transition from current pose
        self._target_pose = target_pose.copy()
        self._transition_duration = duration
        self._transition_start_time = time.time()
        self._in_transition = True
        
        logger.info(f"BasePoseLayer: New target set, duration={duration:.2f}s")
        logger.debug(f"  Target: {target_pose}")
    
    def set_current_pose(self, pose: RobotPose):
        """
        Update the current pose (used for initialization).
        
        Args:
            pose: Current robot pose
        """
        self._current_pose = pose.copy()
        if not self._in_transition:
            self._target_pose = pose.copy()
    
    def get_pose(self, current_time: float) -> RobotPose:
        """
        Get the current pose, interpolating if in transition.
        
        Args:
            current_time: Current time in seconds
            
        Returns:
            Current interpolated pose
        """
        if not self._in_transition:
            return self._current_pose.copy()
        
        # Calculate transition progress
        elapsed = current_time - self._transition_start_time
        
        if elapsed >= self._transition_duration:
            # Transition complete
            self._current_pose = self._target_pose.copy()
            self._in_transition = False
            logger.debug("BasePoseLayer: Transition complete")
            return self._current_pose.copy()
        
        # Smooth easing (cosine ease-in-out)
        progress = elapsed / self._transition_duration
        smooth_progress = (1.0 - np.cos(np.pi * progress)) / 2.0
        
        # Interpolate from start to target
        start_pose = self._current_pose if elapsed == 0 else self._current_pose
        interpolated = start_pose.blend(self._target_pose, smooth_progress)
        
        return interpolated


class IdleLayer(MovementLayer):
    """
    Layer that adds background idle animations (e.g., antenna wiggling).
    
    Applies additive sinusoidal movements to antennas when enabled.
    """
    
    def __init__(self, amplitude: float = 15.0, frequency: float = 0.5):
        """
        Initialize the idle animation layer.
        
        Args:
            amplitude: Oscillation amplitude in degrees (±amplitude)
            frequency: Oscillation frequency in Hz
        """
        self.amplitude = amplitude
        self.frequency = frequency
        self._enabled = False
        self._start_time = time.time()
        
        logger.info(f"IdleLayer initialized (amplitude={amplitude}°, frequency={frequency}Hz)")
    
    def is_active(self) -> bool:
        """Check if idle animations are enabled."""
        return self._enabled
    
    def enable(self, enabled: bool = True):
        """
        Enable or disable idle animations.
        
        Args:
            enabled: True to enable, False to disable
        """
        if enabled and not self._enabled:
            self._start_time = time.time()  # Reset animation phase
            logger.info("IdleLayer: Enabled")
        elif not enabled and self._enabled:
            logger.info("IdleLayer: Disabled")
        
        self._enabled = enabled
    
    def get_pose(self, current_time: float) -> Optional[RobotPose]:
        """
        Compute idle animation contribution.
        
        Args:
            current_time: Current time in seconds
            
        Returns:
            Pose delta to apply, or None if inactive
        """
        if not self._enabled:
            return None
        
        # Calculate sinusoidal position
        elapsed = current_time - self._start_time
        angle_rad = 2.0 * math.pi * self.frequency * elapsed
        antenna_offset = self.amplitude * math.sin(angle_rad)
        
        # Return pose with only antenna deltas
        # Note: This is an additive delta, not absolute position
        return RobotPose(
            roll=0.0,
            pitch=0.0,
            yaw=0.0,
            antennas=(antenna_offset, -antenna_offset),  # Mirror antennas
            body_yaw=0.0
        )
    
    def apply(self, base_pose: RobotPose, current_time: float) -> RobotPose:
        """
        Apply idle animation on top of base pose.
        
        Args:
            base_pose: Base pose to modify
            current_time: Current time in seconds
            
        Returns:
            Modified pose with idle animation applied
        """
        if not self._enabled:
            return base_pose
        
        delta = self.get_pose(current_time)
        if delta is None:
            return base_pose
        
        # Apply delta to antennas only
        result = base_pose.copy()
        result.antennas = (
            base_pose.antennas[0] + delta.antennas[0],
            base_pose.antennas[1] + delta.antennas[1]
        )
        
        return result
