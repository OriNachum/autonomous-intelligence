import torch
import sounddevice as sd
import asyncio
from typing import AsyncGenerator, Tuple
import numpy as np
import logging
from datetime import datetime
import time
from functools import wraps
import argparse
import re
from models import build_model
import torch

# import subprocess
# import threading   
# import sounddevice as sd
# import os 
# import asyncio
# import logging
# import time
# from functools import wraps
# from datetime import datetime
# import argparse
from kokoro import generate, phonemize
# import asyncio
# from typing import AsyncGenerator, Tuple
# import numpy as np




# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(f'tts_log_{datetime.now().strftime("%Y%m%d_%H%M%S")}.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger('TTS_System')

def timing_decorator(func):
    @wraps(func)
    def wrapper(*args, **kwargs):
        start_time = time.perf_counter()
        logger.info(f"Starting {func.__name__}")
        try:
            result = func(*args, **kwargs)
            end_time = time.perf_counter()
            execution_time = end_time - start_time
            logger.info(f"Completed {func.__name__} in {execution_time:.3f} seconds")
            return result
        except Exception as e:
            end_time = time.perf_counter()
            execution_time = end_time - start_time
            logger.error(f"Error in {func.__name__} after {execution_time:.3f} seconds: {str(e)}")
            raise
    return wrapper

def async_timing_decorator(func):
    @wraps(func)
    async def wrapper(*args, **kwargs):
        start_time = time.perf_counter()
        logger.info(f"Starting async {func.__name__}")
        try:
            result = await func(*args, **kwargs)
            end_time = time.perf_counter()
            execution_time = end_time - start_time
            logger.info(f"Completed async {func.__name__} in {execution_time:.3f} seconds")
            return result
        except Exception as e:
            end_time = time.perf_counter()
            execution_time = end_time - start_time
            logger.error(f"Error in async {func.__name__} after {execution_time:.3f} seconds: {str(e)}")
            raise
    return wrapper

import torch
import sounddevice as sd
import asyncio
import numpy as np
import logging
from typing import AsyncGenerator, Tuple, List

class KokoroPytorchSpeaker:
    def __init__(self):
        logger.info("Initializing Speaker class")
        self.logger = logging.getLogger('TTS_System.Speaker')
        self.device = 'cuda' if torch.cuda.is_available() else 'cpu'
        logger.info(f"Running with torch {self.device}")
        self.MODEL = build_model('kokoro-v0_19.pth', self.device)
        self.VOICE_NAME = 'af'  # Default voice
        self.VOICEPACK = torch.load(f'voices/{self.VOICE_NAME}.pt', weights_only=True).to(self.device)
        logger.info(f'Loaded voice: {self.VOICE_NAME}')
        # Warm up
        _, _ = generate(self.MODEL, "ta", self.VOICEPACK, lang=self.VOICE_NAME[0])
        logger.info(f'Initial generation finished')

    def split_into_chunks(self, text: str) -> List[str]:
        """Split text into chunks based on punctuation and natural breaks."""
        # Define gap indicators (punctuation marks that indicate natural pauses)
        #gap_markers = r'[;]
        gap_markers = r'[.!?;:\n]'
        
        # Split text into chunks at gap markers
        chunks = re.split(f'({gap_markers})', text)
        
        # Combine each chunk with its punctuation
        processed_chunks = []
        for i in range(0, len(chunks)-1, 2):
            if i+1 < len(chunks):
                chunk = chunks[i] + chunks[i+1]
            else:
                chunk = chunks[i]
            if chunk.strip():
                processed_chunks.append(chunk.strip())
                
        # Handle any remaining text without punctuation
        if chunks[-1].strip() and len(chunks) % 2 == 1:
            processed_chunks.append(chunks[-1].strip())
            
        return processed_chunks

    async def generate_audio(self, text: str, queue: asyncio.Queue):
        """Generate audio chunks based on natural text breaks."""
        try:
            self.logger.info(f"Starting text chunking and phoneme generation for text: {len(text)} chars")
            start_time = time.perf_counter()
            
            # Split text into natural chunks
            text_chunks = self.split_into_chunks(text)
            self.logger.info(f"Split into {len(text_chunks)} chunks based on punctuation")
            
            for i, chunk_text in enumerate(text_chunks):
                chunk_start = time.perf_counter()
                
                # Generate phonemes for this chunk
                phonemes = phonemize(chunk_text, self.VOICE_NAME[0])
                
                if not phonemes.strip():
                    continue
                
                # Generate audio for the chunk
                audio, _ = generate(self.MODEL, "", self.VOICEPACK,
                                  lang=self.VOICE_NAME[0], ps=phonemes)
                
                if isinstance(audio, torch.Tensor):
                    audio = audio.cpu().numpy()
                
                # Check for silence at start and end with 1ms padding
                audio_start = np.where(np.abs(audio) > 0.01)[0]
                if len(audio_start) > 0:
                    start_idx = 0 #max(0, audio_start[0] - int(0.01 * 24000))  # Keep 1ms of silence
                    end_idx = min(len(audio), audio_start[-1] + int(0.005 * 24000))  # Keep 1ms of silence
                    audio = audio[start_idx:end_idx]
                
                chunk_time = time.perf_counter() - chunk_start
                duration = len(audio) / 24000
                self.logger.info(f"Generated audio for chunk {i+1}/{len(text_chunks)} "
                               f"({len(chunk_text)} chars, {duration:.3f}s) in {chunk_time:.3f} seconds")
                
                await queue.put((audio, 24000))

            # Signal end of generation
            await queue.put((None, None))
            
        except Exception as e:
            self.logger.error(f"Error in generation: {e}")
            await queue.put((None, None))
            raise

    async def play_audio(self, queue: asyncio.Queue):
        """Play audio chunks from the queue."""
        try:
            while True:
                chunk, sample_rate = await queue.get()
                if chunk is None:
                    break
                
                chunk_duration = len(chunk) / sample_rate
                self.logger.info(f"Playing chunk of {chunk_duration:.3f} seconds")
                
                chunk_play_start = time.perf_counter()
                sd.play(chunk, sample_rate)
                sd.wait()
                chunk_play_time = time.perf_counter() - chunk_play_start
                
                self.logger.info(f"Chunk played in {chunk_play_time:.3f} seconds")
                queue.task_done()
                
        except Exception as e:
            self.logger.error(f"Error in playback: {e}")

    @async_timing_decorator    
    async def speak_kokoro_stream(self, text: str):
        """Stream audio generation and playback with parallel processing."""
        self.logger.info(f"Starting parallel generation and playback for text: {len(text)} chars")
        start_time = time.perf_counter()
        
        # Create queue for communication between generator and player
        queue = asyncio.Queue(maxsize=2)  # Small queue size to prevent too much buffering
        
        # Start both tasks immediately and let them run in parallel
        generator_task = asyncio.create_task(self.generate_audio(text, queue))
        player_task = asyncio.create_task(self.play_audio(queue))
        
        # Don't await immediately - let both tasks run independently
        pending = {generator_task, player_task}
        
        try:
            # Wait for tasks to complete, but allow them to run independently
            while pending:
                done, pending = await asyncio.wait(
                    pending,
                    return_when=asyncio.FIRST_COMPLETED
                )
                
                # Check for exceptions in completed tasks
                for task in done:
                    try:
                        await task
                    except Exception as e:
                        self.logger.error(f"Task failed with error: {e}")
                        # Cancel remaining tasks
                        for t in pending:
                            t.cancel()
                        raise
        
        except Exception as e:
            self.logger.error(f"Error in stream processing: {e}")
            raise
        
        finally:
            total_time = time.perf_counter() - start_time
            self.logger.info(f"Stream processing completed in {total_time:.3f} seconds")
    def speak_kokoro_stream_wrapper(self, text: str):
        """
        Synchronous wrapper for streaming playback.
        """
        asyncio.run(self.speak_kokoro_stream(text))
            
def main():
    logger.info("Starting TTS application")
    parser = argparse.ArgumentParser(description='Text-to-Speech System')
    parser.add_argument('text', help='Text to be spoken')
    parser.add_argument('--engine', choices=['kokoro', 'piper'], default='piper',
                      help='TTS engine to use (default: piper)')
    parser.add_argument('--mode', choices=['sync', 'async', 'stream'], default='sync',
                      help='Execution mode (default: sync)')
    parser.add_argument('--session', action='store_true',
                      help='Use session mode for Kokoro (only applicable with kokoro engine)')
    
    args = parser.parse_args()
    logger.info(f"Parsed arguments: engine={args.engine}, mode={args.mode}, session={args.session}")
    
    start_time = time.perf_counter()

    try:
        fixed_text = args.text.replace('\!', '!')
        speaker = KokoroPytorchSpeaker()
        if args.mode == 'stream':
            speaker.speak_kokoro_stream_wrapper(fixed_text)
        else:
            speaker.speak_kokoro_sync(fixed_text)
        total_time = time.perf_counter() - start_time
        logger.info(f"Total execution time: {total_time:.3f} seconds")

    except Exception as e:
        logger.error(f"Application error: {str(e)}")
        raise

if __name__ == "__main__":
    main()