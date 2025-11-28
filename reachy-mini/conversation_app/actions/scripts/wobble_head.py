"""Script for wobbling the robot's head in circles."""
import asyncio
import math


async def execute(make_request, create_head_pose, tts_queue, params):
    """
    Make the robot wobble its head in circular motion.
    
    Args:
        make_request: Function to make HTTP requests
        create_head_pose: Function to create head pose
        tts_queue: TTS queue for speech synthesis
        params: Dictionary with duration, radius, and speed parameters
    """
    duration = params.get('duration', 2.0)
    radius = params.get('radius', 15.0)  # degrees
    speed = params.get('speed', 1.0)  # circles per second
    speech = params.get('speech')
    
    # Handle speech if provided
    if speech and tts_queue:
        await tts_queue.enqueue_text(speech)
    
    # Calculate number of points for smooth circular motion
    points_per_circle = 20
    step_duration = 1.0 / (speed * points_per_circle)
    total_steps = int(duration / step_duration)
    
    # Perform circular wobble motion
    for i in range(total_steps):
        # Calculate angle for circular motion
        angle = (2 * math.pi * i) / points_per_circle
        
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


