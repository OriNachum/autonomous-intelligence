
"""Script for making the robot's head move dizzy in slow circles."""
import asyncio
import math


async def execute(make_request, create_head_pose, tts_queue, params):
    """
    Make the robot look dizzy by moving its head in slow circles.
    
    Args:
        make_request: Function to make HTTP requests
        create_head_pose: Function to create head pose
        tts_queue: TTS queue for speech synthesis
        params: Dictionary with duration, radius, and speed parameters
    """
    try:
        duration = float(params.get('duration', 5.0))
    except (ValueError, TypeError):
        duration = 5.0
        
    try:
        radius = float(params.get('radius', 20.0))
    except (ValueError, TypeError):
        radius = 15.0
        
    # If radius is 0, default to 15.0 (likely LLM hallucination or parsing issue)
    if radius == 0:
        radius = 15.0
        
    try:
        speed = float(params.get('speed', 0.1))
    except (ValueError, TypeError):
        speed = 0.2
    speech = params.get('speech')
    
    # Handle speech if provided
    if speech and tts_queue:
        await tts_queue.enqueue_text(speech)
    
    # Use a fixed update rate for smooth motion (10 Hz)
    UPDATE_RATE = 10
    step_duration = 1.0 / UPDATE_RATE
    
    # Calculate total steps
    total_steps = int(duration * UPDATE_RATE)
    
    # Perform smooth circular dizzy motion
    for i in range(total_steps):
        # Calculate current time
        t = i * step_duration
        
        # Calculate angle (2 * pi * speed * t)
        angle = 2 * math.pi * speed * t
        
        # Calculate roll and pitch for circular motion
        roll = radius * math.sin(angle)
        pitch = radius * math.cos(angle)
        
        # Create head pose
        pose = create_head_pose(roll=roll, pitch=pitch, degrees=True)
        await make_request("POST", "/api/move/goto", json_data={"head_pose": pose, "duration": step_duration})
        
        # Wait for this step to complete
        await asyncio.sleep(step_duration)
    
    # Return to neutral
    pose_neutral = create_head_pose()
    return await make_request("POST", "/api/move/goto", json_data={"head_pose": pose_neutral, "duration": 0.5})


