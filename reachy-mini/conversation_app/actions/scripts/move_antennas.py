"""
Script for move_antennas tool.
Moves the robot's antennas independently.
"""
import math


async def execute(make_request, create_head_pose, tts_queue, params):
    """Execute the move_antennas tool."""
    left = params.get('left')
    right = params.get('right')
    speech = params.get('speech')
    
    # Handle speech if provided
    if speech and tts_queue:
        await tts_queue.enqueue_text(speech)
    
    if left is not None and right is not None:
        # Robust parsing for antenna positions
        try:
            left_angle = float(left)
        except (ValueError, TypeError):
            return {'error': 'Invalid left antenna position', 'status': 'failed'}
            
        try:
            right_angle = float(right)
        except (ValueError, TypeError):
            return {'error': 'Invalid right antenna position', 'status': 'failed'}
            
        try:
            duration = float(params.get('duration', 2.0))
        except (ValueError, TypeError):
            duration = 2.0
        
        antennas_array = [left_angle, right_angle]
        payload = {'antennas': antennas_array, 'duration': duration}
        return await make_request('POST', '/api/move/goto', json_data=payload)
    else:
        return {'error': 'Both left and right antenna positions must be specified', 'status': 'failed'}


