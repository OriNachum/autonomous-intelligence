"""
Script for move_antennas tool.
Moves the robot's antennas independently.
"""


async def execute(controller, tts_queue, params):
    """Execute the move_antennas tool."""
    import asyncio
    
    left = params.get('left')
    right = params.get('right')
    speech = params.get('speech')
    duration = params.get('duration', 2.0)
    
    # Handle speech if provided
    if speech and tts_queue:
        await tts_queue.enqueue_text(speech)
    
    if left is not None and right is not None:
        # Robust parsing for antenna positions
        try:
            left_angle = float(left)
        except (ValueError, TypeError):
            return {'error': 'Invalid left antenna position', 'status': 'failed'}
            
        try:
            right_angle = float(right)
        except (ValueError, TypeError):
            return {'error': 'Invalid right antenna position', 'status': 'failed'}
            
        try:
            parsed_duration = float(duration)
            if parsed_duration < 1:
                parsed_duration = 1.0
        except (ValueError, TypeError):
            parsed_duration = 2.0        

        antennas_array = [right_angle, left_angle]  # Note: order is [right, left]
        
        # Use controller to move antennas
        await asyncio.to_thread(controller.move_smoothly_to, duration=parsed_duration, antennas=antennas_array)
        
        return {"status": "success"}
    else:
        return {'error': 'Both left and right antenna positions must be specified', 'status': 'failed'}
