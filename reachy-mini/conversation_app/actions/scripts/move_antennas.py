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
        #antennas_array = [math.radians(left), math.radians(right)]
        antennas_array = [left, right]
        payload = {'antennas': antennas_array, 'duration': params.get('duration', 2.0)}
        return await make_request('POST', '/api/move/goto', json_data=payload)
    else:
        return {'error': 'Both left and right antenna positions must be specified', 'status': 'failed'}


