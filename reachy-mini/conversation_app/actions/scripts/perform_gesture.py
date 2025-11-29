"""Script for performing gestures with the robot."""
import asyncio
import math


async def execute(controller, tts_queue, params):
    """
    Perform a predefined gesture sequence.
    
    Args:
        controller: ReachyGateway instance for robot control
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
            # Wave with head and antennas
            try:
                duration = float(params.get('duration', 0.8))
            except (ValueError, TypeError):
                duration = 0.8
            
            try:
                angle = float(params.get('angle', 10.0))
            except (ValueError, TypeError):
                angle = 10.0
            
            await asyncio.to_thread(controller.move_smoothly_to, duration=duration, pitch=angle)
            await asyncio.sleep(duration)
            await asyncio.to_thread(controller.move_smoothly_to, duration=duration, pitch=0)
            
            await asyncio.sleep(0.5)
            await asyncio.to_thread(controller.move_smoothly_to, duration=0.5, antennas=[math.degrees(math.radians(30)), math.degrees(math.radians(30))])
            await asyncio.sleep(0.5)
            await asyncio.to_thread(controller.move_smoothly_to, duration=2.0, antennas=[0.0, 0.0])
        
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
            
            await asyncio.to_thread(controller.move_smoothly_to, duration=duration, pitch=angle)
            await asyncio.sleep(duration)
            await asyncio.to_thread(controller.move_smoothly_to, duration=duration, pitch=0)
        
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
            
            await asyncio.to_thread(controller.move_smoothly_to, duration=duration, yaw=-angle)
            await asyncio.sleep(duration)
            await asyncio.to_thread(controller.move_smoothly_to, duration=duration, yaw=angle)
            await asyncio.sleep(duration)
            await asyncio.to_thread(controller.move_smoothly_to, duration=duration, yaw=0)
        
        elif gesture == "thinking":
            # Tilt head and one antenna
            await asyncio.to_thread(
                controller.move_smoothly_to,
                duration=1.5,
                roll=15,
                pitch=5,
                antennas=[20, -10]
            )
        
        elif gesture == "celebration":
            # Excited movements
            for _ in range(2):
                await asyncio.to_thread(controller.move_smoothly_to, duration=0.4, antennas=[40, 40])
                await asyncio.sleep(0.4)
                await asyncio.to_thread(controller.move_smoothly_to, duration=0.4, antennas=[-20, -20])
                await asyncio.sleep(0.4)
            await asyncio.to_thread(controller.move_smoothly_to, duration=2.0, antennas=[0.0, 0.0])
        
        return {"status": "success", "gesture": gesture}
    except Exception as e:
        return {"status": "error", "gesture": gesture, "error": str(e)}
