"""Script for moving the robot's head to a specific target pose."""
import asyncio


async def execute(make_request, create_head_pose, tts_queue, params):
    """
    Move the robot's head to a specific pose (roll, pitch, yaw).
    
    Args:
        make_request: Function to make HTTP requests
        create_head_pose: Function to create head pose
        tts_queue: TTS queue for speech synthesis
        params: Dictionary with roll, pitch, yaw, duration parameters
    """
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
        duration = float(params.get('duration', 1.0))
    except (ValueError, TypeError):
        duration = 1.0
        
    speech = params.get('speech')
    
    # Handle speech if provided
    if speech and tts_queue:
        await tts_queue.enqueue_text(speech)
    
    # Create head pose with specified angles
    pose = create_head_pose(roll=roll, pitch=pitch, yaw=yaw, degrees=True)

    
    # Send movement command
    result = await make_request(
        "POST", 
        "/api/move/goto", 
        json_data={"head_pose": pose, "duration": duration}
    )
    
    # Wait for movement to complete
    await asyncio.sleep(duration)
    
    return result


