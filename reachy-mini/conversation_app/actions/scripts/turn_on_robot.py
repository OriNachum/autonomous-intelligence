"""
Script for turn_on_robot tool.
Turns on the robot's motors and activates all systems.
"""


async def execute(make_request, create_head_pose, tts_queue, params):
    """Execute the turn_on_robot tool."""
    speech = params.get('speech')
    
    result = await make_request('POST', '/api/motors/set_mode/enabled')
    
    # Handle speech if provided (after turning on)
    if speech and tts_queue:
        await tts_queue.enqueue_text(speech)
    
    return result


