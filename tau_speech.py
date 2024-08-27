import os
import pygame
import time
import logging
from clients.face_expression_emitter import FaceExpressionEmitter

# Set up logging
logging.basicConfig(level=logging.DEBUG, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class SpeechQueue:
    def __init__(self, folder_path):
        self.emitter = FaceExpressionEmitter()
        self.emitter.connect()
        logger.info("FaceExpressionEmitter connected")
        self.talking = False
        self.last_emitted_talking = None
        self._folder_path = folder_path
        logger.debug(f"SpeechQueue initialized with folder path: {folder_path}")

    def process_folder(self):
        files = sorted(os.listdir(self._folder_path))
        logger.info(f"Processing folder. Found {len(files)} files.")
        for file in files:
            if file.endswith(".mp3") or file.endswith(".wav"):
                path = os.path.join(self._folder_path, file)
                logger.debug(f"Processing file: {file}")
                self.play_mp3(path)
                os.remove(path)  # Remove the file after playing
                logger.info(f"Removed file after playing: {file}")

    def play_mp3(self, path):
        logger.info(f"Playing {path}")
        try:
            pygame.mixer.music.load(path)
            pygame.mixer.music.play()
            while pygame.mixer.music.get_busy():
                self.emitter.emit_expression("happy", self.talking)
                self.talking = not self.talking
                pygame.time.Clock().tick(10)  # Adjust playback speed
            logger.debug("Finished playing audio file")
        except pygame.error as e:
            logger.error(f"Error playing audio file {path}: {str(e)}")

    def reset(self):
        logger.info("Resetting SpeechQueue")
        try:
            pygame.mixer.init()
            logger.debug("Pygame mixer initialized")
            self.talking = False
            self.emitter.emit_expression("happy", self.talking)
            logger.debug("Emitted 'happy' expression with talking=False")
        except pygame.error as e:
            logger.error(f"Error initializing pygame mixer: {str(e)}")

if __name__ == "__main__":
    logger.info("Starting Speech Queue application")
    try:
        pygame.mixer.init()
        logger.debug("Pygame mixer initialized")
    except pygame.error as e:
        logger.error(f"Failed to initialize pygame mixer: {str(e)}")
        exit(1)

    # Define the folder path to monitor
    folder_path = "./speech_folder"
    logger.info(f"Monitoring folder: {folder_path}")

    # Create the folder if it doesn't exist
    if not os.path.exists(folder_path):
        os.makedirs(folder_path)
        logger.info(f"Created folder: {folder_path}")

    speech_queue = SpeechQueue(folder_path)

    try:
        logger.info("Entering main loop")
        while True:
            # Process the folder for new files
            speech_queue.process_folder()
            
            # If the folder is empty, wait before checking again
            if not os.listdir(folder_path):
                logger.debug("Folder is empty, waiting before next check")
                time.sleep(1)  # Wait for 1 second before checking again
    except KeyboardInterrupt:
        logger.info("Received keyboard interrupt, shutting down")
    except Exception as e:
        logger.error(f"An unexpected error occurred: {str(e)}", exc_info=True)
    finally:
        logger.info("Quitting pygame mixer")
        pygame.mixer.quit()
        logger.info("Application shutdown complete")
