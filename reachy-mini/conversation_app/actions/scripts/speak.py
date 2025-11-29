"""Script for speaking text through TTS."""
import asyncio


async def execute(controller, tts_queue, params):
    """
    Speak text aloud through text-to-speech.
    
    Args:
        controller: ReachyGateway instance (not used in this script)
        tts_queue: TTS queue for speech synthesis
        params: Dictionary with text parameter
    
    Returns:
        Success status dictionary
    """
    text = params.get('text', '')
    
    if not text:
        return {"error": "No text provided", "status": "failed"}
    
    # Check if tts_queue is available
    if tts_queue is None:
        return {"error": "TTS queue not available", "status": "failed"}
    
    # Enqueue text for speech synthesis
    await tts_queue.enqueue_text(text)
    
    return {"status": "success", "text": text}
