"""
Script for look_at_direction tool.
Makes the robot look in a specific direction.
"""


async def execute(make_request, create_head_pose, tts_queue, params):
    """Execute the look_at_direction tool."""
    direction = params.get('direction', 'forward').lower()
    speech = params.get('speech')
    
    # Handle speech if provided
    if speech and tts_queue:
        await tts_queue.enqueue_text(speech)
    
    if direction == 'up':
        pose = create_head_pose(pitch=-30, degrees=True)
    elif direction == 'down':
        pose = create_head_pose(pitch=30, degrees=True)
    elif direction == 'left':
        pose = create_head_pose(yaw=45, degrees=True)
    elif direction == 'right':
        pose = create_head_pose(yaw=-45, degrees=True)
    else:
        pose = create_head_pose()
    
    payload = {'head_pose': pose, 'duration': params.get('duration', 2.0)}
    return await make_request('POST', '/api/move/goto', json_data=payload)


