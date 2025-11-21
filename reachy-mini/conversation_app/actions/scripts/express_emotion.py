"""Script for expressing emotions with the robot."""
import math


async def execute(make_request, create_head_pose, tts_queue, params):
    """
    Make the robot express an emotion using head and antenna movements.
    
    Args:
        make_request: Function to make HTTP requests
        create_head_pose: Function to create head pose
        tts_queue: TTS queue for speech synthesis
        params: Dictionary with emotion parameter
    """
    emotion = params.get('emotion', 'neutral').lower()
    speech = params.get('speech')
    
    # Handle speech if provided
    if speech and tts_queue:
        await tts_queue.enqueue_text(speech)
    
    if emotion == "happy":
        # Lift head slightly and antennas up
        head_pose = create_head_pose(z=5, pitch=-5, degrees=True, mm=True)
        await make_request("POST", "/api/move/goto", json_data={
            "head_pose": head_pose,
            "antennas": [math.radians(30), math.radians(30)],
            "duration": 1.5
        })
        
    elif emotion == "sad":
        # Lower head and antennas down
        head_pose = create_head_pose(z=-5, pitch=10, degrees=True, mm=True)
        await make_request("POST", "/api/move/goto", json_data={
            "head_pose": head_pose,
            "antennas": [math.radians(-20), math.radians(-20)],
            "duration": 2.0
        })
        
    elif emotion == "curious":
        # Tilt head to the side
        head_pose = create_head_pose(roll=20, degrees=True)
        await make_request("POST", "/api/move/goto", json_data={
            "head_pose": head_pose,
            "antennas": [math.radians(15), math.radians(-15)],
            "duration": 1.5
        })
        
    elif emotion == "surprised":
        # Quick upward movement
        head_pose = create_head_pose(z=10, pitch=-15, degrees=True, mm=True)
        await make_request("POST", "/api/move/goto", json_data={
            "head_pose": head_pose,
            "antennas": [math.radians(45), math.radians(45)],
            "duration": 0.8
        })
        
    elif emotion == "confused":
        # Alternate antenna positions
        head_pose = create_head_pose(roll=15, degrees=True)
        await make_request("POST", "/api/move/goto", json_data={
            "head_pose": head_pose,
            "antennas": [math.radians(25), math.radians(-25)],
            "duration": 1.5
        })
        
    else:  # neutral
        pose = create_head_pose()
        await make_request("POST", "/api/move/goto", json_data={"head_pose": pose, "duration": 2.0})
    
    return {"status": "success", "emotion": emotion}


