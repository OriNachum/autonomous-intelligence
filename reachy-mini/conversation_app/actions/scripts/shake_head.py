"""Script for shaking the robot's head."""
import asyncio


async def execute(gateway, tts_queue, params):
    """
    Make the robot shake its head (yaw left and right).
    
    Args:
        gateway: ReachyGateway instance for robot control
        tts_queue: TTS queue for speech synthesis
        params: Dictionary with duration and angle parameters
    """
    
    try:
        duration = float(params.get('duration', 1.0))
    except (ValueError, TypeError):
        duration = 1.0
        
    try:
        angle = float(params.get('angle', 20.0))
    except (ValueError, TypeError):
        angle = 20.0
        
    speech = params.get('speech')
    
    # Handle speech if provided
    if speech and tts_queue:
        await tts_queue.enqueue_text(speech)
    
    # Shake left
    await asyncio.to_thread(gateway.move_smoothly_to, duration=duration, yaw=-angle)
    await asyncio.sleep(duration)
    
    # Shake right
    await asyncio.to_thread(gateway.move_smoothly_to, duration=duration, yaw=angle)
    await asyncio.sleep(duration)
    
    # Return to neutral
    await asyncio.to_thread(gateway.move_smoothly_to, duration=duration, yaw=0)
    
    return {"status": "success"}

