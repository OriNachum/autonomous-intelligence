"""Script for nodding the robot's head."""
import asyncio


async def execute(controller, tts_queue, params):
    """
    Make the robot nod its head (pitch up and down).
    
    Args:
        controller: ReachyGateway instance for robot control
        tts_queue: TTS queue for speech synthesis
        params: Dictionary with duration and angle parameters
    """
    try:
        duration = float(params.get('duration', 1.0))
    except (ValueError, TypeError):
        duration = 1.0
        
    try:
        angle = float(params.get('angle', 15.0))
    except (ValueError, TypeError):
        angle = 15.0
        
    speech = params.get('speech')
    
    # Handle speech if provided
    if speech and tts_queue:
        await tts_queue.enqueue_text(speech)
    
    # Nod down using controller
    await asyncio.to_thread(controller.move_smoothly_to, duration=duration, pitch=angle)
    
    # Wait for movement to complete
    await asyncio.sleep(duration)
    
    # Return to neutral
    await asyncio.to_thread(controller.move_smoothly_to, duration=duration, pitch=0)
    
    return {"status": "success"}
