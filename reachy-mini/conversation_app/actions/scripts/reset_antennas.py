"""
Script for reset_antennas tool.
Resets both antennas to their neutral position (0 degrees).
"""


async def execute(gateway, tts_queue, params):
    """Execute the reset_antennas tool."""
    import asyncio
    
    speech = params.get('speech')
    
    # Handle speech if provided
    if speech and tts_queue:
        await tts_queue.enqueue_text(speech)
    
    try:
        duration = float(params.get('duration', 2.0))
    except (ValueError, TypeError):
        duration = 2.0
    
    # Reset antennas to neutral using controller
    await asyncio.to_thread(gateway.move_smoothly_to, duration=duration, antennas=[0.0, 0.0])
    
    return {"status": "success"}
