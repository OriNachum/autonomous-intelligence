import subprocess
import threading   
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