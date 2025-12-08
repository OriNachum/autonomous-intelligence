"""
Script for turn_off_robot tool.
Turns off the robot's motors and deactivates systems.
"""


async def execute(gateway, tts_queue, params):
    """Execute the turn_off_robot tool."""
    speech = params.get('speech')
    
    # Handle speech if provided (before turning off)
    if speech and tts_queue:
        await tts_queue.enqueue_text(speech)
    
    # Use controller's smooth turn off method
    if gateway:
        try:
            gateway.turn_off_smoothly()
            return {"status": "success", "message": "Robot gracefully turned off"}
        except Exception as e:
            return {"status": "error", "error": str(e)}
    
    return {"status": "error", "error": "Gateway not available"}
