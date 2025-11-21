"""
Script for get_robot_state tool.
Gets the current full state of the Reachy Mini robot.
"""


async def execute(make_request, create_head_pose, tts_queue, params):
    """Execute the get_robot_state tool."""
    return await make_request('GET', '/api/state/full')


