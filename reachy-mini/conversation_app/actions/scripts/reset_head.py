"""
Script for reset_head tool.
Resets the robot's head to the default neutral position.
"""


async def execute(make_request, create_head_pose, tts_queue, params):
    """Execute the reset_head tool."""
    speech = params.get('speech')
    
    # Handle speech if provided
    if speech and tts_queue:
        await tts_queue.enqueue_text(speech)
    
    try:
        duration = float(params.get('duration', 2.0))
    except (ValueError, TypeError):
        duration = 2.0
    
    pose = create_head_pose()
    payload = {'head_pose': pose, 'duration': duration}
    return await make_request('POST', '/api/move/goto', json_data=payload)


