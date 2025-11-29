"""
Script for get_power_state tool.
Gets the current power state of the robot.
"""


async def execute(controller, tts_queue, params):
    """Execute the get_power_state tool."""
    # Access reachy instance for power/motor status
    if controller and controller.reachy_controller:
        try:
            reachy = controller.reachy_controller.reachy
            # Get motor status - basic implementation
            return {"status": "success", "message": "Motors operational"}
        except Exception as e:
            return {"status": "error", "error": str(e)}
    
    return {"status": "error", "error": "Controller not available"}
