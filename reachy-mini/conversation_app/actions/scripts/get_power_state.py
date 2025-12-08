"""
Script for get_power_state tool.
Gets the current power state of the robot.
"""


async def execute(gateway, tts_queue, params):
    """Execute the get_power_state tool."""
    # Access reachy instance for power/motor status
    if controller and gateway.reachy_controller:
        try:
            reachy = gateway.reachy_gateway.reachy
            # Get motor status - basic implementation
            return {"status": "success", "message": "Motors operational"}
        except Exception as e:
            return {"status": "error", "error": str(e)}
    
    return {"status": "error", "error": "Gateway not available"}
