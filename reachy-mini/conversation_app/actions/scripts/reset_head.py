"""
Script for reset_head tool.
Resets the robot's head to the default neutral position.
"""


async def execute(gateway, tts_queue, params):
    """Execute the reset_head tool."""
    import asyncio
    
    speech = params.get('speech')
    
    # Handle speech if provided
    if speech and tts_queue:
        await tts_queue.enqueue_text(speech)
    
    try:
        duration = float(params.get('duration', 2.0))
    except (ValueError, TypeError):
        duration = 2.0
    
    # Reset head to neutral position using controller
    await asyncio.to_thread(gateway.move_smoothly_to, duration=duration, roll=0, pitch=0, yaw=0)
    
    return {"status": "success"}
