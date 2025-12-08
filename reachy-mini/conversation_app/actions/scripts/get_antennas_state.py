"""
Script for get_antennas_state tool.
Gets the current state of the robot's antennas.
"""


async def execute(gateway, tts_queue, params):
    """Execute the get_antennas_state tool."""
    # Get current state from controller
    if gateway:
        state = gateway.get_current_state()
        # state is (roll, pitch, yaw, antennas, body_yaw)
        return {
            "status": "success",
            "antennas_position": state[3]  # antennas is [right, left] in degrees
        }
    
    return {"status": "error", "error": "Gateway not available"}
