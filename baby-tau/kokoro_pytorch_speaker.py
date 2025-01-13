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
from kokoro import generate
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

class KokoroPytorchSpeaker:
    def __init__(self, initializing_notification=True):
        logger.info("Initializing Speaker class")
        self.logger = logging.getLogger('TTS_System.Speaker')
        self.device = 'cuda' if torch.cuda.is_available() else 'cpu'
        logger.info(f"Running with torch {self.device}")
        self.MODEL = build_model('kokoro-v0_19.pth', self.device)
        self.VOICE_NAMES = [
            'af', # Default voice is a 50-50 mix of Bella & Sarah
            'af_bella', 'af_sarah', 'am_adam', 'am_michael',
            'bf_emma', 'bf_isabella', 'bm_george', 'bm_lewis',
            'af_nicole', 'af_sky',
        ]
        self.VOICE_NAME = self.VOICE_NAMES[0] 
        self.VOICEPACK = torch.load(f'voices/{self.VOICE_NAME}.pt', weights_only=True).to(self.device)
        logger.info(f'Loaded voice: {self.VOICE_NAME}')
        # Warm up the model
        audio, out_ps = generate(self.MODEL, "Initializing", self.VOICEPACK, lang=self.VOICE_NAME[0])
        if initializing_notification:
            sd.play(audio, 24000)
            sd.wait()

        logger.info(f'Initial generation finished')

    @timing_decorator
    def speak_kokoro_sync(self, text):
        self.logger.info(f"Processing text synchronously with Kokoro (length: {len(text)} chars)")
        start_time = time.perf_counter()
        audio, out_ps = generate(self.MODEL, text, self.VOICEPACK, lang=self.VOICE_NAME[0])
        generation_time = time.perf_counter() - start_time
        self.logger.info(f"Audio generation completed in {generation_time:.3f} seconds")
        
        start_time = time.perf_counter()
        sd.play(audio, 24000)
        sd.wait()
        playback_time = time.perf_counter() - start_time
        self.logger.info(f"Audio playback completed in {playback_time:.3f} seconds")

    async def generate_stream(self, text: str) -> AsyncGenerator[Tuple[np.ndarray, int], None]:
        """
        Generate audio in two chunks: first sentence, then the rest.
        
        Args:
            text: Input text to synthesize
            
        Yields:
            Tuple of (audio_chunk, sample_rate)
        """
        self.logger.info(f"Starting streaming generation for text: {len(text)} chars")
        
        # Split into first sentence and rest
        # Look for common sentence endings
        sample_rate = 24000
        sentence_endings = ['. ', '! ', '? ', '.\n', '!\n', '?\n']
        current_pos = 0
        remaining_text = text.strip()

        while remaining_text:
            # Find the next sentence ending
            next_end = float('inf')
            for ending in sentence_endings:
                pos = remaining_text.find(ending)
                if pos != -1 and pos < next_end:
                    next_end = pos + len(ending) - 1

            # If no sentence ending found, treat remaining text as final sentence
            if next_end == float('inf'):
                current_sentence = remaining_text
                remaining_text = ""
            else:
                current_sentence = remaining_text[:next_end].strip()
                remaining_text = remaining_text[next_end:].strip()

            # Generate audio for current sentence if it's not empty
            if current_sentence:
                chunk_start = time.perf_counter()
                audio_chunk, out_ps = generate(self.MODEL, current_sentence, self.VOICEPACK, lang=self.VOICE_NAME[0])
                chunk_time = time.perf_counter() - chunk_start
                self.logger.info(f"Generated sentence ({len(current_sentence)} chars) in {chunk_time:.3f} seconds")
                self.logger.info(f"Sentence: {current_sentence}")
                
                if isinstance(audio_chunk, torch.Tensor):
                    audio_chunk = audio_chunk.cpu().numpy()
                yield audio_chunk, sample_rate
            
            await asyncio.sleep(0.01)  # Give other tasks a chance to run
        await asyncio.sleep(0.01)

    @async_timing_decorator    
    async def speak_kokoro_stream(self, text: str):
        """
        Speak text using streaming generation and playback, with playback overlapping generation.
        """
        self.logger.info(f"Starting streaming playback for text: {len(text)} chars")
        start_time = time.perf_counter()
        flag = False

        # Create a queue for audio chunks
        queue = asyncio.Queue()
        
        # Create a task for audio playback
        async def play_audio():
            while True:
                try:
                    chunk, sample_rate = await queue.get()
                    if chunk is None:  # Sentinel value to stop playback
                        break

                    # Check for silence at start and end
                    audio_start = np.where(np.abs(chunk) > 0.01)[0]
                    if len(audio_start) > 0:
                        start_idx = max(0, audio_start[0] - int(0.02 * sample_rate))  # Keep 50ms of silence
                        end_idx = min(len(chunk), audio_start[-1] + int(0.02 * sample_rate))  # Keep 100ms of silence
                        chunk = chunk[start_idx:end_idx]

                    chunk_play_start = time.perf_counter()
                    self.logger.info(f"Chunk playback starting")
                    sd.play(chunk, sample_rate)
                    self.logger.info(f"Chunk playback started")
                    sd.wait()
                    chunk_play_time = time.perf_counter() - chunk_play_start
                    self.logger.info(f"Chunk playback completed in {chunk_play_time:.3f} seconds")
                    queue.task_done()
                except Exception as e:
                    self.logger.error(f"Error in playback: {e}")
                    break

        # Start the playback task
        playback_task = asyncio.create_task(play_audio())
        
        try:
            # Generate and queue chunks
            async for chunk, sample_rate in self.generate_stream(text):
                if not flag:
                    generation_time = time.perf_counter() - start_time
                    self.logger.info(f"Time to first generated chunk: {generation_time:.3f} seconds")
                    flag = True
                
                await queue.put((chunk, sample_rate))
                
            # Signal playback task to stop
            await queue.put((None, None))
            
            # Wait for playback to complete
            await playback_task
            
        except Exception as e:
            self.logger.error(f"Error in generation: {e}")
            # Ensure playback task is cleaned up
            if not playback_task.done():
                playback_task.cancel()
                try:
                    await playback_task
                except asyncio.CancelledError:
                    pass

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