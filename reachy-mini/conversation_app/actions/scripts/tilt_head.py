"""
Script for tilt_head tool.
Tilts the robot's head to the left or right.
"""


async def execute(gateway, tts_queue, params):
    """Execute the tilt_head tool."""
    import asyncio
    
    direction = params.get('direction', 'left')
    
    try:
        angle = float(params.get('angle', 15.0))
    except (ValueError, TypeError):
        angle = 15.0
        
    speech = params.get('speech')
    
    # Handle speech if provided
    if speech and tts_queue:
        await tts_queue.enqueue_text(speech)
    
    roll_angle = angle if direction.lower() == 'left' else -1*angle
    
    try:
        duration = float(params.get('duration', 2.0))
    except (ValueError, TypeError):
        duration = 2.0
    
    # Use controller to tilt smoothly
    await asyncio.to_thread(gateway.move_smoothly_to, duration=duration, roll=roll_angle)
    
    return {"status": "success"}
