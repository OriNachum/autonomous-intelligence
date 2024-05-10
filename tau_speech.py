import os
import pygame
import time

from clients.face_expression_emitter import FaceExpressionEmitter

class SpeechQueue:
    def __init__(self, folder_path):
        self.emitter = FaceExpressionEmitter()
        self.emitter.connect()
        self.talking = False
        self.last_emitted_talking = None
        self._folder_path = folder_path

    def process_folder(self):
        files = sorted(os.listdir(self._folder_path))
        for file in files:
            if file.endswith(".mp3") or file.endswith(".wav"):
                path = os.path.join(self._folder_path, file)
                self.play_mp3(path)
                os.remove(path)  # Remove the file after playing

    def play_mp3(self, path):
        print(f"playing {path}")
        pygame.mixer.music.load(path)
        pygame.mixer.music.play()
        while pygame.mixer.music.get_busy():
            pygame.time.Clock().tick(10)  # Adjust playback speed

    def reset(self):
        pygame.mixer.init()

if __name__ == "__main__":
    pygame.mixer.init()

    # Define the folder path to monitor
    folder_path = "./speech_folder"

    # Create the folder if it doesn't exist
    if not os.path.exists(folder_path):
        os.makedirs(folder_path)

    speech_queue = SpeechQueue(folder_path)

    try:
        while True:
            # Process the folder for new files
            speech_queue.process_folder()
            
            # If the folder is empty, wait before checking again
            if not os.listdir(folder_path):
                time.sleep(1)  # Wait for 1 second before checking again
    finally:
        pygame.mixer.quit()
