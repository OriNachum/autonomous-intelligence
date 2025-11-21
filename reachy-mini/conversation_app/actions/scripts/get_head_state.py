"""
Script for get_head_state tool.
Gets the current state of the robot's head.
"""


async def execute(make_request, create_head_pose, tts_queue, params):
    """Execute the get_head_state tool."""
    full_state = await make_request('GET', '/api/state/full')
    
    if 'head_pose' in full_state:
        return {'head_pose': full_state['head_pose']}
    
    return full_state


