"""
Script for move_head tool.
Moves the robot's head to a target pose.
"""


async def execute(make_request, create_head_pose, tts_queue, params):
    """Execute the move_head tool."""
    speech = params.get('speech')
    
    # Handle speech if provided
    if speech and tts_queue:
        await tts_queue.enqueue_text(speech)
    
    # Robust parameter parsing with defaults
    try:
        x = float(params.get('x', 0.0))
    except (ValueError, TypeError):
        x = 0.0
        
    try:
        y = float(params.get('y', 0.0))
    except (ValueError, TypeError):
        y = 0.0
        
    try:
        z = float(params.get('z', 0.0))
    except (ValueError, TypeError):
        z = 0.0
        
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
        duration = float(params.get('duration', 2.0))
    except (ValueError, TypeError):
        duration = 2.0
    
    # Boolean parameters with defaults
    degrees = params.get('degrees', True)
    mm = params.get('mm', True)
    
    pose = create_head_pose(x, y, z, roll, pitch, yaw, degrees, mm)
    
    payload = {'head_pose': pose, 'duration': duration}
    return await make_request('POST', '/api/move/goto', json_data=payload)


