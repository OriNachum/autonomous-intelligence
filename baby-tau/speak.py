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

class Speaker:
    def __init__(self):
        logger.info("Initializing Speaker class")
        self.logger = logging.getLogger('TTS_System.Speaker')
    
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
    def speak_kokoro_session(self, text):
        self.logger.info(f"Processing text with Kokoro session (length: {len(text)} chars)")
        session = self.create_session()
        kokoro = Kokoro.from_session(session, "voices.json", espeak_config=None)
        samples, sample_rate = kokoro.create("ta", voice="af_sky", speed=1.0, lang="en-us")
        start_time = time.perf_counter()
        samples, sample_rate = kokoro.create(text, voice="af_sky", speed=1.0, lang="en-us")
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
        kokoro = Kokoro("kokoro-v0_19.onnx", "voices.json")
        stream = kokoro.create_stream(text, voice="af_sky", speed=1.0, lang="en-us")
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
        kokoro = Kokoro("kokoro-v0_19.onnx", "voices.json")
        samples, sample_rate = kokoro.create("te", voice="af_sky", speed=1.0, lang="en-us")
        start_time = time.perf_counter()
        samples, sample_rate = kokoro.create(text, voice="af_sky", speed=1.0, lang="en-us")
        generation_time = time.perf_counter() - start_time
        self.logger.info(f"Audio generation completed in {generation_time:.3f} seconds")
        
        start_time = time.perf_counter()
        sd.play(samples, sample_rate)
        sd.wait()
        playback_time = time.perf_counter() - start_time
        self.logger.info(f"Audio playback completed in {playback_time:.3f} seconds")

    @timing_decorator
    def speak_piper(self, text):
        self.logger.info(f"Processing text with Piper (length: {len(text)} chars)")
        try:
            start_time = time.perf_counter()
            echo = subprocess.Popen(['echo', text], stdout=subprocess.PIPE)
            piper = subprocess.Popen(
                ['piper', '--cuda', '--model', './en_US-lessac-high.onnx', '--output_raw'],
                stdin=echo.stdout,
                stdout=subprocess.PIPE
            )
            generation_time = time.perf_counter() - start_time
            self.logger.info(f"Audio generation completed in {generation_time:.3f} seconds")
            aplay = subprocess.Popen(
                ['aplay', '-f', 'S16_LE', '-c1', '-r22050'],
                stdin=piper.stdout
            )
            aplay.wait()
            total_time = time.perf_counter() - start_time
            self.logger.info(f"Piper processing and playback completed in {total_time:.3f} seconds")
        except Exception as e:
            self.logger.error(f"Error in Piper processing: {str(e)}")
            raise

    @timing_decorator
    def speak_espeak(self, text):
        self.logger.info(f"Processing text with eSpeak (length: {len(text)} chars)")
        try:
            start_time = time.perf_counter()
            subprocess.run(["espeak", "-v", "en-us", text], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            total_time = time.perf_counter() - start_time
            self.logger.info(f"eSpeak processing completed in {total_time:.3f} seconds")
        except Exception as e:
            self.logger.error(f"Error in eSpeak processing: {str(e)}")
            raise

    def speak_async(self, text):
        self.logger.info("Starting asynchronous speech thread")
        threading.Thread(target=self.speak_espeak, args=(text,)).start()

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