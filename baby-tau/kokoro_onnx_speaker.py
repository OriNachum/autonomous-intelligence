import subprocess
import threading   
from kokoro_onnx import Kokoro
import onnxruntime as ort
from onnxruntime import InferenceSession
import sounddevice as sd
import os 
import asyncio
import logging
import time
from functools import wraps
from datetime import datetime
import argparse

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

class KokoroOnnxSpeaker:
    def __init__(self):
        logger.info("Initializing Speaker class")
        self.logger = logging.getLogger('TTS_System.Speaker')
        self.session = self.create_session()
        self.logger.info(f"Processing text with Kokoro session (length: {len(text)} chars)")
        self.kokoro = Kokoro.from_session(self.session, "voices.json", espeak_config=None)
        # active loading
        samples, sample_rate = self.kokoro.create("ta", voice="af_sky", speed=1.0, lang="en-us")
    
    @timing_decorator
    def create_session(self):
        session_options = ort.SessionOptions()
        cpu_count = os.cpu_count()
        self.logger.info(f"Creating session with {cpu_count} CPU threads")
        session_options.intra_op_num_threads = cpu_count
        providers = ort.get_available_providers()
        self.logger.info(f"Available ONNX providers: {providers}")
        session = InferenceSession("kokoro-v0_19.onnx", providers=['CUDAExecutionProvider'], sess_options=session_options)
        return session

    @timing_decorator
    def speak(self, text):
        start_time = time.perf_counter()
        samples, sample_rate = self.kokoro.create(text, voice="af_sky", speed=1.0, lang="en-us")
        generation_time = time.perf_counter() - start_time
        self.logger.info(f"Audio generation completed in {generation_time:.3f} seconds")
        
        start_time = time.perf_counter()
        sd.play(samples, sample_rate)
        sd.wait()
        playback_time = time.perf_counter() - start_time
        self.logger.info(f"Audio playback completed in {playback_time:.3f} seconds")

    def speak_kokoro_async_wrapper(self, text):
        asyncio.run(self.speak_kokoro_async(text))

    @async_timing_decorator
    async def speak_kokoro_async(self, text):
        self.logger.info(f"Processing text asynchronously with Kokoro (length: {len(text)} chars)")
        stream = self.kokoro.create_stream(text, voice="af_sky", speed=1.0, lang="en-us")
        count = 0
        async for samples, sample_rate in stream:
            count += 1
            self.logger.info(f"Processing stream chunk {count}")
            start_time = time.perf_counter()
            sd.play(samples, sample_rate)
            sd.wait()
            chunk_time = time.perf_counter() - start_time
            self.logger.info(f"Chunk {count} played in {chunk_time:.3f} seconds")

    @timing_decorator
    def speak_kokoro_sync(self, text):
        self.logger.info(f"Processing text synchronously with Kokoro (length: {len(text)} chars)")
        samples, sample_rate = self.kokoro.create("te", voice="af_sky", speed=1.0, lang="en-us")
        start_time = time.perf_counter()
        samples, sample_rate = kokoro.create(text, voice="af_sky", speed=1.0, lang="en-us")
        generation_time = time.perf_counter() - start_time
        self.logger.info(f"Audio generation completed in {generation_time:.3f} seconds")
        
        start_time = time.perf_counter()
        sd.play(samples, sample_rate)
        sd.wait()
        playback_time = time.perf_counter() - start_time
        self.logger.info(f"Audio playback completed in {playback_time:.3f} seconds")

def main():
    logger.info("Starting TTS application")
    parser = argparse.ArgumentParser(description='Text-to-Speech System')
    parser.add_argument('text', help='Text to be spoken')
    parser.add_argument('--engine', choices=['kokoro', 'piper'], default='piper',
                      help='TTS engine to use (default: piper)')
    parser.add_argument('--mode', choices=['sync', 'async'], default='sync',
                      help='Execution mode (default: sync)')
    parser.add_argument('--session', action='store_true',
                      help='Use session mode for Kokoro (only applicable with kokoro engine)')
    
    args = parser.parse_args()
    logger.info(f"Parsed arguments: engine={args.engine}, mode={args.mode}, session={args.session}")
    
    speaker = Speaker()
    start_time = time.perf_counter()

    try:
        if args.engine == 'piper':
            if args.session:
                logger.warning("Session mode is only available for Kokoro engine. Ignoring --session flag.")
            if args.mode == 'async':
                logger.warning("Async mode is not available for Piper. Using sync mode.")
            speaker.speak_piper(args.text)
        
        elif args.engine == 'kokoro':
            if args.mode == 'async':
                speaker.speak_kokoro_async_wrapper(args.text)
            elif args.session:
                speaker.speak_kokoro_session(args.text)
            else:
                speaker.speak_kokoro_sync(args.text)

        total_time = time.perf_counter() - start_time
        logger.info(f"Total execution time: {total_time:.3f} seconds")

    except Exception as e:
        logger.error(f"Application error: {str(e)}")
        raise

if __name__ == "__main__":
    main()