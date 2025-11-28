"""Script for performing gestures with the robot."""
import asyncio
import math


async def execute(make_request, create_head_pose, tts_queue, params):
    """
    Perform a predefined gesture sequence.
    
    Args:
        make_request: Function to make HTTP requests
        create_head_pose: Function to create head pose
        tts_queue: TTS queue for speech synthesis
        params: Dictionary with gesture parameter
    """
    gesture = params.get('gesture', '').lower()
    speech = params.get('speech')
    
    # Handle speech if provided
    if speech and tts_queue:
        await tts_queue.enqueue_text(speech)
    
    # Validate gesture parameter
    valid_gestures = ['greeting', 'yes', 'no', 'thinking', 'celebration']
    if gesture not in valid_gestures:
        return {"status": "error", "error": f"Invalid gesture: {gesture}"}
    
    try:
        if gesture == "greeting":
            # Wave with head and antennas - call nod_head logic
            try:
                duration = float(params.get('duration', 0.8))
            except (ValueError, TypeError):
                duration = 0.8
            
            try:
                angle = float(params.get('angle', 10.0))
            except (ValueError, TypeError):
                angle = 10.0
            
            pose_down = create_head_pose(pitch=angle, degrees=True)
            await make_request("POST", "/api/move/goto", json_data={"head_pose": pose_down, "duration": duration})
            await asyncio.sleep(duration)
            pose_neutral = create_head_pose()
            await make_request("POST", "/api/move/goto", json_data={"head_pose": pose_neutral, "duration": duration})
            
            await asyncio.sleep(0.5)
            await make_request("POST", "/api/move/goto", json_data={"antennas": [math.radians(30), math.radians(30)], "duration": 0.5})
            await asyncio.sleep(0.5)
            await make_request("POST", "/api/move/goto", json_data={"antennas": [0.0, 0.0], "duration": 2.0})
        
        elif gesture == "yes":
            # Nod yes
            try:
                duration = float(params.get('duration', 0.8))
            except (ValueError, TypeError):
                duration = 0.8
            
            try:
                angle = float(params.get('angle', 20.0))
            except (ValueError, TypeError):
                angle = 20.0
            
            pose_down = create_head_pose(pitch=angle, degrees=True)
            await make_request("POST", "/api/move/goto", json_data={"head_pose": pose_down, "duration": duration})
            await asyncio.sleep(duration)
            pose_neutral = create_head_pose()
            return await make_request("POST", "/api/move/goto", json_data={"head_pose": pose_neutral, "duration": duration})
        
        elif gesture == "no":
            # Shake no
            try:
                duration = float(params.get('duration', 0.7))
            except (ValueError, TypeError):
                duration = 0.7
            
            try:
                angle = float(params.get('angle', 25.0))
            except (ValueError, TypeError):
                angle = 25.0
            
            pose_left = create_head_pose(yaw=-angle, degrees=True)
            await make_request("POST", "/api/move/goto", json_data={"head_pose": pose_left, "duration": duration})
            await asyncio.sleep(duration)
            pose_right = create_head_pose(yaw=angle, degrees=True)
            await make_request("POST", "/api/move/goto", json_data={"head_pose": pose_right, "duration": duration})
            await asyncio.sleep(duration)
            pose_neutral = create_head_pose()
            return await make_request("POST", "/api/move/goto", json_data={"head_pose": pose_neutral, "duration": duration})
        
        elif gesture == "thinking":
            # Tilt head and one antenna
            head_pose = create_head_pose(roll=15, pitch=5, degrees=True)
            await make_request("POST", "/api/move/goto", json_data={
                "head_pose": head_pose,
                "antennas": [math.radians(20), math.radians(-10)],
                "duration": 1.5
            })
        
        elif gesture == "celebration":
            # Excited movements
            for _ in range(2):
                await make_request("POST", "/api/move/goto", json_data={"antennas": [math.radians(40), math.radians(40)], "duration": 0.4})
                await asyncio.sleep(0.4)
                await make_request("POST", "/api/move/goto", json_data={"antennas": [math.radians(-20), math.radians(-20)], "duration": 0.4})
                await asyncio.sleep(0.4)
            await make_request("POST", "/api/move/goto", json_data={"antennas": [0.0, 0.0], "duration": 2.0})
        
        return {"status": "success", "gesture": gesture}
    except Exception as e:
        return {"status": "error", "gesture": gesture, "error": str(e)}


