import torch
import torchaudio
import asyncio
from typing import AsyncGenerator, Tuple, List
import numpy as np
import logging
from datetime import datetime
import time
from functools import wraps
import argparse
import re
from kokoro import KPipeline
from IPython.display import display, Audio

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
    def __init__(self):
        logger.info("Initializing Speaker class")
        self.logger = logging.getLogger('TTS_System.Speaker')
        self.device = 'cuda' if torch.cuda.is_available() else 'cpu'
        logger.info(f"Running with torch {self.device}")
        pipeline = KPipeline(lang_code='a') # <= make sure lang_code matches voice

        self.MODEL = build_model('kokoro-v0_19.pth', self.device)
        self.VOICE_NAME = 'af'  # Default voice
        self.VOICEPACK = torch.load(f'voices/{self.VOICE_NAME}.pt', weights_only=True).to(self.device)
        logger.info(f'Loaded voice: {self.VOICE_NAME}')
        # Warm up
        _, _ = generate(self.MODEL, "ta", self.VOICEPACK, lang=self.VOICE_NAME[0])
        logger.info(f'Initial generation finished')

    def split_into_chunks(self, text: str) -> List[str]:
        """Split text into chunks based on punctuation and natural breaks."""
        gap_markers = r'[.!?;:\n]'
        chunks = re.split(f'({gap_markers})', text)
        
        processed_chunks = []
        for i in range(0, len(chunks)-1, 2):
            if i+1 < len(chunks):
                chunk = chunks[i] + chunks[i+1]
            else:
                chunk = chunks[i]
            if chunk.strip():
                processed_chunks.append(chunk.strip())
                
        if chunks[-1].strip() and len(chunks) % 2 == 1:
            processed_chunks.append(chunks[-1].strip())
            
        return processed_chunks

    async def generate_audio(self, text: str, queue: asyncio.Queue):
        """Generate audio chunks based on natural text breaks."""
        try:
            self.logger.info(f"Starting text chunking and phoneme generation for text: {len(text)} chars")
            start_time = time.perf_counter()
            
            text_chunks = self.split_into_chunks(text)
            self.logger.info(f"Split into {len(text_chunks)} chunks based on punctuation")
            
            for i, chunk_text in enumerate(text_chunks):
                chunk_start = time.perf_counter()
                
                phonemes = phonemize(chunk_text, self.VOICE_NAME[0])
                
                if not phonemes.strip():
                    continue
                
                audio, _ = generate(self.MODEL, "", self.VOICEPACK,
                                  lang=self.VOICE_NAME[0], ps=phonemes)
                
                if isinstance(audio, torch.Tensor):
                    audio = audio.cpu()
                
                # Check for silence at start and end with 1ms padding
                audio_numpy = audio.numpy() if isinstance(audio, torch.Tensor) else audio
                audio_start = np.where(np.abs(audio_numpy) > 0.01)[0]
                if len(audio_start) > 0:
                    start_idx = 0
                    end_idx = min(len(audio_numpy), audio_start[-1] + int(0.005 * 24000))
                    audio = audio[start_idx:end_idx]
                
                chunk_time = time.perf_counter() - chunk_start
                duration = len(audio) / 24000
                self.logger.info(f"Generated audio for chunk {i+1}/{len(text_chunks)} "
                               f"({len(chunk_text)} chars, {duration:.3f}s) in {chunk_time:.3f} seconds")
                
                await queue.put((audio, 24000))

            await queue.put((None, None))
            
        except Exception as e:
            self.logger.error(f"Error in generation: {e}")
            await queue.put((None, None))
            raise

    async def play_audio(self, queue: asyncio.Queue):
        """Play audio chunks from the queue using torchaudio."""
        try:
            while True:
                chunk, sample_rate = await queue.get()
                if chunk is None:
                    break
                
                chunk_duration = len(chunk) / sample_rate
                self.logger.info(f"Playing chunk of {chunk_duration:.3f} seconds")
                
                chunk_play_start = time.perf_counter()
                
                # Ensure chunk is a torch tensor
                if not isinstance(chunk, torch.Tensor):
                    chunk = torch.tensor(chunk)
                
                # Reshape if needed (torchaudio expects [channels, samples])
                if len(chunk.shape) == 1:
                    chunk = chunk.unsqueeze(0)
                
                # Play audio using torchaudio
                torchaudio.play(chunk, sample_rate)
                
                # Wait for playback to complete (approximate)
                await asyncio.sleep(chunk_duration)
                
                chunk_play_time = time.perf_counter() - chunk_play_start
                self.logger.info(f"Chunk played in {chunk_play_time:.3f} seconds")
                queue.task_done()
                
        except Exception as e:
            self.logger.error(f"Error in playback: {e}")

    @async_timing_decorator    
    async def speak_async(self, text: str):
        """Stream audio generation and playback with parallel processing."""
        self.logger.info(f"Starting parallel generation and playback for text: {len(text)} chars")
        start_time = time.perf_counter()
        
        queue = asyncio.Queue(maxsize=2)
        
        generator_task = asyncio.create_task(self.generate_audio(text, queue))
        player_task = asyncio.create_task(self.play_audio(queue))
        
        pending = {generator_task, player_task}
        
        try:
            while pending:
                done, pending = await asyncio.wait(
                    pending,
                    return_when=asyncio.FIRST_COMPLETED
                )
                
                for task in done:
                    try:
                        await task
                    except Exception as e:
                        self.logger.error(f"Task failed with error: {e}")
                        for t in pending:
                            t.cancel()
                        raise
        
        except Exception as e:
            self.logger.error(f"Error in stream processing: {e}")
            raise
        
        finally:
            total_time = time.perf_counter() - start_time
            self.logger.info(f"Stream processing completed in {total_time:.3f} seconds")

    def speak(self, text: str):
        generator = pipeline(
            text, voice='af_heart', # <= change voice here
            speed=1, split_pattern=r'\n+'
        )
        for i, (gs, ps, audio) in enumerate(generator):
            print(i)  # i => index
            print(gs) # gs => graphemes/text
            print(ps) # ps => phonemes
            display(Audio(data=audio, rate=24000, autoplay=i==0))

        return 
        """Synchronous wrapper for streaming playback."""
        asyncio.run(self.speak_async(text))
            
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
        speaker.speak(fixed_text)
        total_time = time.perf_counter() - start_time
        logger.info(f"Total execution time: {total_time:.3f} seconds")

    except Exception as e:
        logger.error(f"Application error: {str(e)}")
        raise

if __name__ == "__main__":
    main()