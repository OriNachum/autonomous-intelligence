"""
Script for get_head_state tool.
Gets the current state of the robot's head.
"""


async def execute(controller, tts_queue, params):
    """Execute the get_head_state tool."""
    # Get current state from controller
    if controller:
        state = controller.get_current_state()
        # state is (roll, pitch, yaw, antennas, body_yaw)
        return {
            "status": "success",
            "head_pose": {
                "roll": state[0],
                "pitch": state[1],
                "yaw": state[2]
            }
        }
    
    return {"status": "error", "error": "Controller not available"}
