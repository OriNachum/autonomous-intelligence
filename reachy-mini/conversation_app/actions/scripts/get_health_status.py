"""
Script for get_health_status tool.
Gets the overall health status of the robot.
"""


async def execute(gateway, tts_queue, params):
    """Execute the get_health_status tool."""
    # Access reachy instance directly for health status
    if controller and gateway.reachy_controller:
        try:
            reachy = gateway.reachy_gateway.reachy
            # Get health information from reachy instance
            # This is a basic implementation - expand as needed
            return {"status": "success", "message": "Robot is operational"}
        except Exception as e:
            return {"status": "error", "error": str(e)}
    
    return {"status": "error", "error": "Gateway not available"}
