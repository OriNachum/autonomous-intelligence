import threading
import queue
import time
import pygame

class SpeechQueue:
    def __init__(self):
        self._queue = queue.Queue()
        self._thread = threading.Thread(target=self._play_audio)
        self._playing = False
        # Initialize pygame mixer
        pygame.mixer.init()
        self._thread.start()


    def enqueue(self, item):
        self._queue.put(item)

    def clear(self):
        if pygame.mixer.music.get_busy():
            pygame.mixer.music.stop()
        self._queue.queue.clear()

    def _play_audio(self):
        while True:
            if not pygame.mixer.music.get_busy():
                self._playing = True
                item = self._queue.get()       
                play_mp3(item)
            time.sleep(0.05)  # 50 milliseconds delay


    def join(self):
        self._thread.join()


def play_mp3(path):
    # Load the MP3 file
    pygame.mixer.music.load(path)
    # Play the MP3 file
    pygame.mixer.music.play()
 

if "__main__" == __name__:
    # Example usage:
    speech_queue = SpeechQueue()

    # Enqueue some audio files
    speech_queue.enqueue("./modelproviders/speech_0.mp3")
    speech_queue.enqueue("./modelproviders/speech_1.mp3")
    speech_queue.enqueue("./modelproviders/speech_2.mp3")

    # Continue running other tasks while the audio is playing
    input("Enter to exit")

    # Clear the queue if needed
    speech_queue.clear()

    # Wait for the audio playback thread to finish
    speech_queue.join()
