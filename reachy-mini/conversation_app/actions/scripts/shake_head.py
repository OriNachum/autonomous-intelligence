"""Script for shaking the robot's head."""
import asyncio


async def execute(make_request, create_head_pose, tts_queue, params):
    """
    Make the robot shake its head (yaw left and right).
    
    Args:
        make_request: Function to make HTTP requests
        create_head_pose: Function to create head pose
        tts_queue: TTS queue for speech synthesis
        params: Dictionary with duration and angle parameters
    """
    duration = params.get('duration', 1.0)
    angle = params.get('angle', 20.0)
    speech = params.get('speech')
    
    # Handle speech if provided
    if speech and tts_queue:
        await tts_queue.enqueue_text(speech)
    
    # Shake left
    pose_left = create_head_pose(yaw=-angle, degrees=True)
    await make_request("POST", "/api/move/goto", json_data={"head_pose": pose_left, "duration": duration})
    await asyncio.sleep(duration)
    
    # Shake right
    pose_right = create_head_pose(yaw=angle, degrees=True)
    await make_request("POST", "/api/move/goto", json_data={"head_pose": pose_right, "duration": duration})
    await asyncio.sleep(duration)
    
    # Return to neutral
    pose_neutral = create_head_pose()
    return await make_request("POST", "/api/move/goto", json_data={"head_pose": pose_neutral, "duration": duration})


