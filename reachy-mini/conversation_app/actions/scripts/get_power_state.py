"""
Script for get_power_state tool.
Gets the current power state of the robot.
"""


async def execute(make_request, create_head_pose, tts_queue, params):
    """Execute the get_power_state tool."""
    return await make_request('GET', '/api/motors/status')


