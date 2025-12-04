"""
Script for turn_on_robot tool.
Turns on the robot's motors and activates all systems.
"""


async def execute(controller, tts_queue, params):
    """Execute the turn_on_robot tool."""
    speech = params.get('speech')
    
    # Access reachy instance to enable motors
    if controller and controller.reachy_controller:
        try:
            reachy = controller.reachy_controller.reachy
            # Enable motors
            reachy.turn_on()
            
            # Handle speech if provided (after turning on)
            if speech and tts_queue:
                await tts_queue.enqueue_text(speech)
            
            return {"status": "success", "message": "Robot turned on"}
        except Exception as e:
            return {"status": "error", "error": str(e)}
    
    return {"status": "error", "error": "Controller not available"}
