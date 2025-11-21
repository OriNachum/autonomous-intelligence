"""Script for nodding the robot's head."""
import asyncio


async def execute(make_request, create_head_pose, tts_queue, params):
    """
    Make the robot nod its head (pitch up and down).
    
    Args:
        make_request: Function to make HTTP requests
        create_head_pose: Function to create head pose
        tts_queue: TTS queue for speech synthesis
        params: Dictionary with duration and angle parameters
    """
    duration = params.get('duration', 1.0)
    angle = params.get('angle', 15.0)
    speech = params.get('speech')
    
    # Handle speech if provided
    if speech and tts_queue:
        await tts_queue.enqueue_text(speech)
    
    # Nod down
    pose_down = create_head_pose(pitch=angle, degrees=True)
    await make_request("POST", "/api/move/goto", json_data={"head_pose": pose_down, "duration": duration})
    
    # Wait for movement to complete
    await asyncio.sleep(duration)
    
    # Return to neutral
    pose_neutral = create_head_pose()
    return await make_request("POST", "/api/move/goto", json_data={"head_pose": pose_neutral, "duration": duration})


