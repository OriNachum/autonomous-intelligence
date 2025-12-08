"""Script for moving the robot's head to a specific target pose."""
import asyncio


async def execute(gateway, tts_queue, params):
    """
    Move the robot's head to a specific pose (roll, pitch, yaw).
    
    Args:
        gateway: ReachyGateway instance for robot control
        tts_queue: TTS queue for speech synthesis
        params: Dictionary with roll, pitch, yaw, duration parameters
    """
    # Robust parameter parsing with defaults
    try:
        roll = float(params.get('roll', 0.0))
    except (ValueError, TypeError):
        roll = 0.0
        
    try:
        pitch = float(params.get('pitch', 0.0))
    except (ValueError, TypeError):
        pitch = 0.0
        
    try:
        yaw = float(params.get('yaw', 0.0))
    except (ValueError, TypeError):
        yaw = 0.0
        
    try:
        duration = float(params.get('duration', 1.0))
    except (ValueError, TypeError):
        duration = 1.0
        
    speech = params.get('speech')
    
    # Handle speech if provided
    if speech and tts_queue:
        await tts_queue.enqueue_text(speech)
    
    # Move head using controller
    await asyncio.to_thread(gateway.move_smoothly_to, duration=duration, roll=roll, pitch=pitch, yaw=yaw)
    
    # Wait for movement to complete
    await asyncio.sleep(duration)
    
    return {"status": "success"}
