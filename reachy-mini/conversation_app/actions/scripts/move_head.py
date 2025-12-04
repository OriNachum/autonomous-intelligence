"""
Script for move_head tool.
Moves the robot's head to a target pose.
"""


async def execute(controller, tts_queue, params):
    """Execute the move_head tool."""
    import asyncio
    
    speech = params.get('speech')
    
    # Handle speech if provided
    if speech and tts_queue:
        await tts_queue.enqueue_text(speech)
    
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
        duration = float(params.get('duration', 2.0))
    except (ValueError, TypeError):
        duration = 2.0
    
    # Use controller.move_smoothly_to instead of HTTP requests
    # Note: x, y, z parameters are not supported by move_smoothly_to
    # only roll, pitch, yaw are supported for head movements
    await asyncio.to_thread(
        controller.move_smoothly_to,
        duration=duration,
        roll=roll,
        pitch=pitch,
        yaw=yaw
    )
    
    return {"status": "success"}
