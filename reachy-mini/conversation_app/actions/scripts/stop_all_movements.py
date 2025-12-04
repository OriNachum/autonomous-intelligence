"""
Script for stop_all_movements tool.
Emergency stop - immediately halts all robot movements.
"""


async def execute(controller, tts_queue, params):
    """Execute the stop_all_movements tool."""
    speech = params.get('speech')
    
    # Handle speech if provided
    if speech and tts_queue:
        await tts_queue.enqueue_text(speech)
    
    # Access reachy instance to stop motors
    if controller and controller.reachy_controller:
        try:
            reachy = controller.reachy_controller.reachy
            # Disable motors to stop all movement
            reachy.turn_off()
            return {"status": "success", "message": "All movements stopped"}
        except Exception as e:
            return {"status": "error", "error": str(e)}
    
    return {"status": "error", "error": "Controller not available"}
