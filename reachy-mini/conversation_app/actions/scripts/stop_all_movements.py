"""
Script for stop_all_movements tool.
Emergency stop - immediately halts all robot movements.
"""


async def execute(make_request, create_head_pose, tts_queue, params):
    """Execute the stop_all_movements tool."""
    speech = params.get('speech')
    
    # Handle speech if provided
    if speech and tts_queue:
        await tts_queue.enqueue_text(speech)
    
    return await make_request('POST', '/api/motors/set_mode/disabled')


