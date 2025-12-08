"""
Script for look_at_direction tool.
Makes the robot look in a specific direction.
"""


async def execute(gateway, tts_queue, params):
    """Execute the look_at_direction tool."""
    import asyncio
    
    direction = params.get('direction', 'forward').lower()
    speech = params.get('speech')
    
    # Handle speech if provided
    if speech and tts_queue:
        await tts_queue.enqueue_text(speech)
    
    # Validate direction parameter
    valid_directions = ['up', 'down', 'left', 'right', 'forward']
    if direction not in valid_directions:
        direction = 'forward'
    
    # Determine target pose based on direction
    roll, pitch, yaw = 0, 0, 0
    if direction == 'up':
        pitch = -30
    elif direction == 'down':
        pitch = 30
    elif direction == 'left':
        yaw = 45
    elif direction == 'right':
        yaw = -45
    
    try:
        duration = float(params.get('duration', 2.0))
    except (ValueError, TypeError):
        duration = 2.0
    
    # Move using controller
    await asyncio.to_thread(gateway.move_smoothly_to, duration=duration, roll=roll, pitch=pitch, yaw=yaw)
    
    return {"status": "success"}
