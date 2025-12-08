
"""Script for making the robot's head move dizzy in slow circles."""
import asyncio
import math


async def execute(gateway, tts_queue, params):
    """
    Make the robot look dizzy by moving its head in slow circles.
    
    Args:
        gateway: ReachyGateway instance for robot control
        tts_queue: TTS queue for speech synthesis
        params: Dictionary with duration, radius, and speed parameters
    """
    try:
        duration = float(params.get('duration', 5.0))
    except (ValueError, TypeError):
        duration = 5.0
    
    # If duration is 0, default to 5.0 (likely LLM hallucination or parsing issue)
    if duration <= 5:
        duration = 5.0

    try:
        radius = float(params.get('radius', 20.0))
    except (ValueError, TypeError):
        radius = 20.0
    if radius < 20:
        radius = 20.0

    try:
        speed = float(params.get('speed', 0.1))
    except (ValueError, TypeError):
        speed = 0.1
    if speed < 0.1:
        speed = 0.1


    speech = params.get('speech')


    # Handle speech if provided
    if speech and tts_queue:
        await tts_queue.enqueue_text(speech)
    
    # Use a fixed update rate for smooth motion (10 Hz)
    UPDATE_RATE = 10
    step_duration = 1.0 / UPDATE_RATE
    
    # Calculate total steps
    total_steps = int(duration * UPDATE_RATE)
    
    # Perform smooth circular dizzy motion using gateway
    for i in range(total_steps):
        # Calculate current time
        t = i * step_duration
        
        # Calculate angle (2 * pi * speed * t)
        angle = 2 * math.pi * speed * t
        
        # Calculate roll and pitch for circular motion
        roll = radius * math.sin(angle)
        pitch = radius * math.cos(angle)
        
        # Move head using gateway
        await asyncio.to_thread(gateway.move_smoothly_to, duration=step_duration, roll=roll, pitch=pitch, yaw=0)
        
        # Wait for this step to complete
        await asyncio.sleep(step_duration)
    
    # Return to neutral
    await asyncio.to_thread(gateway.move_smoothly_to, duration=0.5, roll=0, pitch=0, yaw=0)
    
    return {"status": "success"}

