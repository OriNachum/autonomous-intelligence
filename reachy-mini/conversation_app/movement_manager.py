#!/usr/bin/env python3
"""
Movement Manager Module

This module manages background antenna movements for Reachy based on operational modes.
Modes:
- STATIC: No background movement (robot is speaking/acting)
- WAITING: Sinusoidal antenna movement (robot is listening/idle)
"""

import logging
import threading
import time
import math
import numpy as np
from typing import Optional

logger = logging.getLogger(__name__)


class MovementManager:
    """Manages background antenna movements based on operational mode."""
    
    # Movement modes
    MODE_STATIC = "STATIC"
    MODE_WAITING = "WAITING"
    
    def __init__(self, reachy_controller):
        """
        Initialize the movement manager.
        
        Args:
            reachy_controller: ReachyController instance for robot control
        """
        self.controller = reachy_controller
        self.mode = self.MODE_STATIC
        self.running = False
        self._thread = None
        self._lock = threading.Lock()
        
        # Animation parameters for WAITING mode
        self.antenna_amplitude = 15.0  # degrees (±15)
        self.animation_frequency = 0.5  # Hz (0.5 cycles per second = 2 seconds per full cycle)
        self.control_rate = 50  # Hz (50 updates per second)
        
        logger.info("MovementManager initialized")
    
    def start(self):
        """Start the background movement thread."""
        if self.running:
            logger.warning("MovementManager is already running")
            return
        
        self.running = True
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()
        logger.info("MovementManager started")
    
    def stop(self):
        """Stop the background movement thread."""
        if not self.running:
            return
        
        self.running = False
        if self._thread:
            self._thread.join(timeout=1.0)
            self._thread = None
        logger.info("MovementManager stopped")
    
    def set_mode(self, mode: str):
        """
        Set the operational mode.
        
        Args:
            mode: Either MODE_STATIC or MODE_WAITING
        """
        with self._lock:
            if mode not in [self.MODE_STATIC, self.MODE_WAITING]:
                logger.warning(f"Invalid mode: {mode}, defaulting to STATIC")
                mode = self.MODE_STATIC
            
            if self.mode != mode:
                old_mode = self.mode
                self.mode = mode
                logger.info(f"Mode changed: {old_mode} → {mode}")
    
    def get_mode(self) -> str:
        """Get the current operational mode."""
        with self._lock:
            return self.mode
    
    def _loop(self):
        """
        Main control loop running at control_rate Hz.
        
        In WAITING mode, continuously updates antenna positions in a sinusoidal pattern.
        In STATIC mode, does nothing (antennas remain at their current position).
        """
        loop_period = 1.0 / self.control_rate
        start_time = time.time()
        
        logger.info(f"Movement loop started (rate: {self.control_rate} Hz)")
        
        while self.running:
            loop_start = time.time()
            
            # Check current mode (thread-safe)
            current_mode = self.get_mode()
            
            if current_mode == self.MODE_WAITING:
                # Calculate time-based sinusoidal position
                elapsed = time.time() - start_time
                
                # Sinusoidal movement: position = amplitude * sin(2π * frequency * time)
                # This creates a smooth oscillation between -amplitude and +amplitude
                angle_rad = 2.0 * math.pi * self.animation_frequency * elapsed
                antenna_position_deg = self.antenna_amplitude * math.sin(angle_rad)
                
                # Convert to radians for set_target
                antenna_position_rad = np.deg2rad(antenna_position_deg)
                
                try:
                    # Get current head pose to maintain head position
                    head_pose_matrix = self.controller.mini.get_current_head_pose()
                    
                    # Set target with only antennas moving (both antennas mirror each other)
                    self.controller.mini.set_target(
                        head=head_pose_matrix,
                        antennas=[antenna_position_rad, antenna_position_rad],
                        body_yaw=None  # Maintain current body yaw
                    )
                    
                    logger.debug(f"Antennas: {antenna_position_deg:.1f}°")
                    
                except Exception as e:
                    logger.error(f"Error updating antenna position: {e}")
            
            # In STATIC mode, do nothing - antennas stay at current position
            
            # Sleep to maintain loop rate
            elapsed = time.time() - loop_start
            sleep_time = max(0, loop_period - elapsed)
            time.sleep(sleep_time)
        
        logger.info("Movement loop stopped")
    
    def cleanup(self):
        """Clean up resources."""
        logger.info("Cleaning up MovementManager")
        self.stop()
