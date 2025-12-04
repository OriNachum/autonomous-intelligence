"""
Script for get_robot_state tool.
Gets the current full state of the Reachy Mini robot.
"""


async def execute(controller, tts_queue, params):
    """Execute the get_robot_state tool."""
    # Get states from controller
    if controller:
        state = controller.get_current_state()
        natural_state = controller.get_current_state_natural()
        
        return {
            "status": "success",
            "raw_state": {
                "roll": state[0],
                "pitch": state[1],
                "yaw": state[2],
                "antennas": state[3],
                "body_yaw": state[4]
            },
            "natural_state": natural_state
        }
    
    return {"status": "error", "error": "Controller not available"}
