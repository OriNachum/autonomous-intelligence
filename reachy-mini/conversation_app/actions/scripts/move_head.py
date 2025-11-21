"""
Script for move_head tool.
Moves the robot's head to a target pose.
"""


async def execute(make_request, create_head_pose, tts_queue, params):
    """Execute the move_head tool."""
    speech = params.get('speech')
    
    # Handle speech if provided
    if speech and tts_queue:
        await tts_queue.enqueue_text(speech)
    
    pose = create_head_pose(
        params.get('x', 0.0),
        params.get('y', 0.0),
        params.get('z', 0.0),
        params.get('roll', 0.0),
        params.get('pitch', 0.0),
        params.get('yaw', 0.0),
        params.get('degrees', True),
        params.get('mm', True)
    )
    
    payload = {'head_pose': pose, 'duration': params.get('duration', 2.0)}
    return await make_request('POST', '/api/move/goto', json_data=payload)


