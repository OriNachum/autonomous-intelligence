#!/usr/bin/env python3
"""
Natural Language Mappings for Robot Parameters

This module provides bidirectional translation between descriptive names
and numeric values for all robot movement parameters.
"""

import logging
import numpy as np
from typing import Union, List, Tuple

logger = logging.getLogger(__name__)

# Natural language mappings for robot movements
NATURAL_MAPPINGS = {
    # Pitch (nodding): up/down movements
    'pitch': {
        'up': 20.0,
        'down': -20.0,
        'slight_up': 10.0,
        'slight_down': -10.0,
        'neutral': 0.0,
    },
    
    # Roll (tilting): side tilt movements
    'roll': {
        'left': 20.0,
        'right': -20.0,
        'slight_left': 10.0,
        'slight_right': -10.0,
        'neutral': 0.0,
    },
    
    # Antennas: expressive movements [right, left]
    'antennas': {
        'happy': [30.0, 30.0],
        'sad': [-30.0, -30.0],
        'curious': [45.0, 45.0],
        'confused': [45.0, -45.0],
        'alert': [15.0, 15.0],
        'neutral': [0.0, 0.0],
    },
    
    # Duration (speed): movement timing in seconds
    'duration': {
        'instant': 0.5,
        'fast': 1.0,
        'normal': 2.0,
        'slow': 4.0,
        'very_slow': 6.0,
    }
}

# Natural direction vectors for yaw and body_yaw
CARDINAL_VECTORS = {
    'front': (0, 1),
    'back': (0, -1),
    'left': (-1, 0),   # Fixed: left should be negative X for proper angle calculation
    'right': (1, 0),   # Fixed: right should be positive X for proper angle calculation
    # Keep compass directions for backward compatibility
    'north': (0, 1),
    'south': (0, -1),
    'west': (1, 0),
    'east': (-1, 0),
}


def name_to_value(parameter_name: str, name: Union[str, float, List]) -> Union[float, List[float], str]:
    """
    Convert a named parameter to its numeric value.
    
    Args:
        parameter_name: Name of the parameter ('pitch', 'roll', 'antennas', 'duration', 'yaw', 'body_yaw')
        name: Named value (e.g., 'up', 'happy', 'fast') or already numeric value or compass direction
        
    Returns:
        Numeric value(s) for the parameter, or special string value for dynamic resolution
        
    Raises:
        ValueError: If the name is not recognized for the given parameter
    """
    # Handle already numeric values (fallback for backward compatibility)
    if isinstance(name, (int, float)):
        return float(name)
    
    if isinstance(name, list):
        return name
    
    # Handle special parameter values that require dynamic resolution
    if isinstance(name, str):
        normalized_name = name.lower().strip()
        if normalized_name in ['return', 'back', 'doa']:
            # Pass through as-is for action_handler to resolve dynamically
            return normalized_name
    
    # Handle natural/compass directions for yaw/body_yaw
    if parameter_name in ['yaw', 'body_yaw'] and isinstance(name, str):
        return parse_direction(name)
    
    # Handle named parameters
    if parameter_name not in NATURAL_MAPPINGS:
        raise ValueError(f"Unknown parameter: {parameter_name}")
    
    # Normalize name (lowercase, replace spaces with underscores)
    normalized_name = name.lower().strip().replace(' ', '_')
    
    if normalized_name not in NATURAL_MAPPINGS[parameter_name]:
        # Try without normalization in case it's a compass direction that failed
        raise ValueError(f"Unknown value '{name}' for parameter '{parameter_name}'. "
                        f"Valid values: {list(NATURAL_MAPPINGS[parameter_name].keys())}")
    
    return NATURAL_MAPPINGS[parameter_name][normalized_name]


def value_to_name(parameter_name: str, value: Union[float, List[float]]) -> str:
    """
    Convert a numeric value to its closest named parameter.
    
    Args:
        parameter_name: Name of the parameter ('pitch', 'roll', 'antennas', 'duration', 'yaw', 'body_yaw')
        value: Numeric value(s)
        
    Returns:
        Named value (e.g., 'up', 'happy', 'fast') or compass direction
    """
    # Handle natural directions for yaw/body_yaw
    if parameter_name in ['yaw', 'body_yaw']:
        # Convert reachy_yaw to angle: angle = -2 * reachy_yaw
        angle = -2.0 * value
        return degrees_to_direction(angle)
    
    # Handle antennas (list of values)
    if parameter_name == 'antennas':
        if not isinstance(value, list):
            value = [value, value]
        
        # Find closest match
        min_distance = float('inf')
        closest_name = 'neutral'
        
        for name, target_values in NATURAL_MAPPINGS['antennas'].items():
            # Calculate Euclidean distance
            distance = np.sqrt((value[0] - target_values[0])**2 + (value[1] - target_values[1])**2)
            if distance < min_distance:
                min_distance = distance
                closest_name = name
        
        return closest_name
    
    # Handle scalar parameters (pitch, roll, duration)
    if parameter_name not in NATURAL_MAPPINGS:
        logger.warning(f"Unknown parameter '{parameter_name}', returning value as-is")
        return str(value)
    
    # Find closest match
    min_distance = float('inf')
    closest_name = 'neutral'
    
    for name, target_value in NATURAL_MAPPINGS[parameter_name].items():
        distance = abs(value - target_value)
        if distance < min_distance:
            min_distance = distance
            closest_name = name
    
    return closest_name


def parse_direction(direction_str: str) -> float:
    """
    Parse natural direction string and convert to Reachy yaw angle in degrees.
    
    Uses vector addition to handle arbitrary direction strings like "front right".
    Reachy's yaw is limited to ±45°, where:
    - Front (0°) = forward = 0° in Reachy
    - Right (90°) = right = -45° in Reachy (max right)
    - Left (-90°) = left = +45° in Reachy (max left)
    - Back (180°) = backward (limited range)
    
    Also supports compass directions for backward compatibility:
    - North (0°) = forward = 0° in Reachy
    - East (90°) = right = -45° in Reachy (max right)
    - West (-90°) = left = +45° in Reachy (max left)
    
    Formula: reachy_yaw = -1 * (angle / 2)
    
    Args:
        direction_str: Natural or compass direction (e.g., "front", "right", "front right", "North East")
    
    Returns:
        Yaw angle in degrees for Reachy, clamped to ±45°
    """
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
    
    # If no valid tokens found, default to front (forward)
    if total_x == 0 and total_y == 0:
        logger.warning(f"No valid direction in '{direction_str}', defaulting to front (0°)")
        return 0.0
    
    # Calculate the angle of the resulting vector relative to front
    # atan2 gives angle from East (positive x-axis), we need from front (positive y-axis)
    angle_rad = np.arctan2(total_x, total_y)  # Note: swapped x and y for front=0
    angle_deg = np.degrees(angle_rad)
    
    # Map angle to Reachy yaw
    # Angle: Right=90°, Left=-90° (or 270°)
    # Reachy: Max Right=-45°, Max Left=+45°
    # Formula: reachy_yaw = -1 * (angle / 2)
    reachy_yaw = -1.0 * (angle_deg / 2.0)
    
    # Clamp to safety limits (±45°)
    MAX_YAW = 45.0
    reachy_yaw = np.clip(reachy_yaw, -MAX_YAW, MAX_YAW)
    
    logger.debug(f"Parsed direction '{direction_str}': angle={angle_deg:.1f}°, "
                f"reachy_yaw={reachy_yaw:.1f}°")
    
    return float(reachy_yaw)


# Keep parse_compass_direction as an alias for backward compatibility
parse_compass_direction = parse_direction


def degrees_to_direction(degrees: float) -> str:
    """
    Convert angle in degrees to nearest natural direction.
    
    Args:
        degrees: Angle in degrees (0=front, 90=left, -90=right)
    
    Returns:
        Natural direction string (e.g., "front", "front right", "right")
    """
    # Normalize to [0, 360)
    degrees = degrees % 360.0
    
    # Quantize to 8 directions (front, front right, right, back right, back, back left, left, front left)
    # Each direction spans 45°
    directions = [
        "front",       # 337.5-22.5 (wraps around 0)
        "front left",  # 22.5-67.5
        "left",        # 67.5-112.5
        "back left",   # 112.5-157.5
        "back",        # 157.5-202.5
        "back right",  # 202.5-247.5
        "right",       # 247.5-292.5
        "front right"  # 292.5-337.5
    ]
    
    # Convert to index (0-7)
    # Add 22.5 to shift boundaries, divide by 45 to get direction
    index = int((degrees + 22.5) / 45.0) % 8
    
    return directions[index]


# Keep degrees_to_compass as an alias for backward compatibility
degrees_to_compass = degrees_to_direction
