#!/usr/bin/env python3
"""
Movement Manager Module

This module manages the unified movement loop for Reachy, compositing
multiple movement layers (base poses, idle animations, gestures) into
a single smooth control flow.
"""

import logging
import threading
import time
import numpy as np
from typing import Optional
from reachy_mini.utils import create_head_pose

try:
    from .robot_pose import RobotPose
    from .movement_layers import BasePoseLayer, IdleLayer
except ImportError:
    from robot_pose import RobotPose
    from movement_layers import BasePoseLayer, IdleLayer

logger = logging.getLogger(__name__)


class MovementManager:
    """
    Manages the unified movement loop with layer composition.
    
    Runs a constant control loop that composites multiple movement sources:
    - Base pose layer: Primary target positions with smooth transitions
    - Idle layer: Background animations (antenna wiggling)
    - Future: Gesture layer for one-off movements
    """
    
    def __init__(self, reachy_controller):
        """
        Initialize the movement manager.
        
        Args:
            reachy_controller: ReachyController instance for robot control
        """
        self.controller = reachy_controller
        self.running = False
        self._thread = None
        self._lock = threading.Lock()
        
        # Movement layers
        self.base_layer = BasePoseLayer()
        self.idle_layer = IdleLayer(amplitude=15.0, frequency=0.5)
        
        # Control loop parameters
        self.control_rate = 50  # Hz (50 updates per second)
        
        # Initialize base layer with current robot state
        current_pose = RobotPose.from_current_state(reachy_controller)
        self.base_layer.set_current_pose(current_pose)
        
        logger.info("MovementManager initialized with layer-based architecture")
        logger.info(f"  Base layer: {current_pose}")
        logger.info(f"  Idle layer: amplitude=15.0°, frequency=0.5Hz")
    
    def start(self):
        """Start the background movement thread."""
        if self.running:
            logger.warning("MovementManager is already running")
            return
        
        self.running = True
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()
        logger.info("MovementManager: Control loop started")
    
    def stop(self):
        """Stop the background movement thread."""
        if not self.running:
            return
        
        self.running = False
        if self._thread:
            self._thread.join(timeout=1.0)
            self._thread = None
        logger.info("MovementManager: Control loop stopped")
    
    def set_target_pose(self, pose: RobotPose, duration: float = 2.0):
        """
        Set a new target pose with smooth transition.
        
        This is the main API for commanding robot movements.
        
        Args:
            pose: Target pose
            duration: Transition duration in seconds
        """
        with self._lock:
            self.base_layer.set_target(pose, duration)
        logger.debug(f"MovementManager: Target pose updated (duration={duration:.2f}s)")
    
    def enable_idle(self, enable: bool = True):
        """
        Enable or disable idle animations.
        
        Args:
            enable: True to enable idle animations, False to disable
        """
        with self._lock:
            self.idle_layer.enable(enable)
        logger.info(f"MovementManager: Idle animations {'enabled' if enable else 'disabled'}")
    
    def get_current_pose(self) -> RobotPose:
        """
        Get the current robot pose.
        
        Returns:
            Current RobotPose
        """
        return RobotPose.from_current_state(self.controller)
    
    def _loop(self):
        """
        Main control loop running at control_rate Hz.
        
        Composites all active layers and sends the final pose to the robot.
        """
        loop_period = 1.0 / self.control_rate
        consecutive_errors = 0
        max_consecutive_errors = 3
        
        logger.info(f"Movement loop started (rate: {self.control_rate} Hz)")
        
        while self.running:
            loop_start = time.time()
            current_time = time.time()
            
            try:
                with self._lock:
                    # 1. Get base pose from base layer
                    final_pose = self.base_layer.get_pose(current_time)
                    
                    # 2. Apply idle layer if active
                    if self.idle_layer.is_active():
                        final_pose = self.idle_layer.apply(final_pose, current_time)
                    
                    # 3. Future: Apply gesture layer if active
                    # if self.gesture_layer.is_active():
                    #     final_pose = self.gesture_layer.apply(final_pose, current_time)
                
                # 4. Apply safety validation
                roll_rad, pitch_rad, yaw_rad, antennas_rad, body_yaw_rad = final_pose.to_radians()
                
                safe_roll, safe_pitch, safe_yaw, safe_antennas, safe_body_yaw = \
                    self.controller.apply_safety_to_movement(
                        roll_rad, pitch_rad, yaw_rad, 
                        antennas_rad, body_yaw_rad
                    )
                
                # 5. Send to robot
                head_pose = create_head_pose(
                    roll=safe_roll,
                    pitch=safe_pitch,
                    yaw=safe_yaw,
                    degrees=False,
                    mm=False
                )
                
                self.controller.mini.set_target(
                    head=head_pose,
                    antennas=list(safe_antennas),
                    body_yaw=safe_body_yaw
                )
                
                # Update tracked body yaw
                self.controller._current_body_yaw = np.degrees(safe_body_yaw)
                
                logger.debug(f"Pose sent: {final_pose}")
                
                # Reset error counter on success
                consecutive_errors = 0
                
            except ConnectionError as e:
                consecutive_errors += 1
                logger.error(f"Connection error in movement loop (attempt {consecutive_errors}/{max_consecutive_errors}): {e}")
                
                if consecutive_errors >= max_consecutive_errors:
                    logger.warning(f"Too many consecutive connection errors, attempting daemon reset...")
                    
                    # Attempt to reset daemon
                    reset_success = self.controller.reset_daemon()
                    
                    if reset_success:
                        logger.info("Daemon reset successful, resuming movement loop")
                        consecutive_errors = 0
                        
                        # Re-initialize base layer with current robot state
                        try:
                            current_pose = RobotPose.from_current_state(self.controller)
                            self.base_layer.set_current_pose(current_pose)
                            logger.info(f"Base layer re-initialized with: {current_pose}")
                        except Exception as reinit_error:
                            logger.error(f"Failed to re-initialize base layer: {reinit_error}")
                    else:
                        logger.error("Daemon reset failed, will retry on next error")
                        consecutive_errors = 0  # Reset counter to try again later
                
                # Apply exponential backoff
                backoff_time = min(5.0, 0.5 * (2 ** consecutive_errors))
                logger.info(f"Backing off for {backoff_time:.1f}s before retry")
                time.sleep(backoff_time)
                
            except Exception as e:
                logger.error(f"Error in movement loop: {e}", exc_info=True)
                consecutive_errors = 0  # Don't count non-connection errors
            
            # Sleep to maintain loop rate
            elapsed = time.time() - loop_start
            sleep_time = max(0, loop_period - elapsed)
            time.sleep(sleep_time)
        
        logger.info("Movement loop stopped")
    
    def cleanup(self):
        """Clean up resources."""
        logger.info("Cleaning up MovementManager")
        self.stop()
