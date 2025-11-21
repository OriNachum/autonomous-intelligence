"""
Script for get_antennas_state tool.
Gets the current state of the robot's antennas.
"""


async def execute(make_request, create_head_pose, tts_queue, params):
    """Execute the get_antennas_state tool."""
    full_state = await make_request('GET', '/api/state/full')
    
    if 'antennas_position' in full_state:
        return {'antennas_position': full_state['antennas_position']}
    
    return full_state


