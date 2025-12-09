"""
Script for look_at_direction tool.
Makes the robot look in a specific direction.
"""


async def execute(gateway, tts_queue, params):
    """Execute the look_at_direction tool."""
    import asyncio
    from conversation_app import mappings
    
    direction = params.get('direction', 'forward')
    speech = params.get('speech')
    
    # Handle speech if provided
    if speech and tts_queue:
        await tts_queue.enqueue_text(speech)
    
    # Parse direction using mappings module
    # This handles complex directions like "front left" -> yaw ~22.5 deg
    yaw = mappings.parse_direction(direction)
    
    # Determine pitch based on direction string
    # mappings.parse_direction only handles yaw (left/right)
    # We need to manually handle up/down for pitch
    pitch = 0.0
    direction_lower = direction.lower()
    
    if 'up' in direction_lower:
        pitch = -20.0
    elif 'down' in direction_lower:
        pitch = 20.0
        
    try:
        duration = float(params.get('duration', 2.0))
    except (ValueError, TypeError):
        duration = 2.0
    
    # Move using controller
    # roll is 0 for look actions
    await asyncio.to_thread(gateway.move_smoothly_to, duration=duration, roll=0.0, pitch=pitch, yaw=yaw)
    
    return {"status": "success", "yaw": yaw, "pitch": pitch}
