"""Script for expressing emotions with the robot."""
import asyncio


async def execute(gateway, tts_queue, params):
    """
    Make the robot express an emotion using head and antenna movements.
    
    Args:
        gateway: ReachyGateway instance for robot control
        tts_queue: TTS queue for speech synthesis
        params: Dictionary with emotion parameter
    """
    emotion = params.get('emotion', 'neutral').lower()
    speech = params.get('speech')
    
    # Handle speech if provided
    if speech and tts_queue:
        await tts_queue.enqueue_text(speech)
    
    # Validate emotion parameter
    valid_emotions = ['happy', 'sad', 'curious', 'surprised', 'confused', 'neutral']
    if emotion not in valid_emotions:
        emotion = 'neutral'
    
    try:
        if emotion == "happy":
            # Lift head slightly and antennas up
            # Note: x, y, z parameters not supported by move_smoothly_to, using pitch only
            await asyncio.to_thread(
                gateway.move_smoothly_to,
                duration=1.5,
                pitch=-5,
                antennas=[30, 30]
            )
            
        elif emotion == "sad":
            # Lower head and antennas down
            await asyncio.to_thread(
                gateway.move_smoothly_to,
                duration=2.0,
                pitch=10,
                antennas=[-20, -20]
            )
            
        elif emotion == "curious":
            # Tilt head to the side
            await asyncio.to_thread(
                gateway.move_smoothly_to,
                duration=1.5,
                roll=20,
                antennas=[15, -15]
            )
            
        elif emotion == "surprised":
            # Quick upward movement
            await asyncio.to_thread(
                gateway.move_smoothly_to,
                duration=0.8,
                pitch=-15,
                antennas=[45, 45]
            )
            
        elif emotion == "confused":
            # Alternate antenna positions
            await asyncio.to_thread(
                gateway.move_smoothly_to,
                duration=1.5,
                roll=15,
                antennas=[25, -25]
            )
            
        else:  # neutral
            await asyncio.to_thread(gateway.move_smoothly_to, duration=2.0, roll=0, pitch=0, yaw=0, antennas=[0, 0])
        
        return {"status": "success", "emotion": emotion}
    except Exception as e:
        return {"status": "error", "emotion": emotion, "error": str(e)}

