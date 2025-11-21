"""
Script for turn_off_robot tool.
Turns off the robot's motors and deactivates systems.
"""


async def execute(make_request, create_head_pose, tts_queue, params):
    """Execute the turn_off_robot tool."""
    speech = params.get('speech')
    
    # Handle speech if provided (before turning off)
    if speech and tts_queue:
        await tts_queue.enqueue_text(speech)
    
    return await make_request('POST', '/api/motors/set_mode/disabled')


