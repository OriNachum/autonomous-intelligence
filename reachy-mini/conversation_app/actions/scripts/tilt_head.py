"""
Script for tilt_head tool.
Tilts the robot's head to the left or right.
"""


async def execute(make_request, create_head_pose, tts_queue, params):
    """Execute the tilt_head tool."""
    direction = params.get('direction', 'left')
    angle = params.get('angle', 15.0)
    speech = params.get('speech')
    
    # Handle speech if provided
    if speech and tts_queue:
        await tts_queue.enqueue_text(speech)
    
    roll_angle = angle if direction.lower() == 'left' else -1*angle
    pose = create_head_pose(roll=roll_angle, degrees=True)
    
    payload = {'head_pose': pose, 'duration': params.get('duration', 2.0)}
    return await make_request('POST', '/api/move/goto', json_data=payload)


