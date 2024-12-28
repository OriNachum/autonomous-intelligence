import threading
import queue
import time
import pygame
import random

from clients.face_expression_emitter import FaceExpressionEmitter

class SpeechQueue:
    def __init__(self):
        self.emitter = FaceExpressionEmitter()
        self.emitter.connect()
        self.talking = False
        self.last_emitted_talking = None
        
        self._queue = queue.Queue()
        self._thread = None

    def enqueue(self, item):
        self._queue.put(item)

    def clear(self):
        if pygame.mixer.music.get_busy():
            pygame.mixer.music.stop()
        self._queue.queue.clear()
        self.talking = False
        self.emitter.emit_expression("normal", self.talking)
        if self._thread is not None:
            self._thread.join()
            self._thread = None


    def _play_audio(self):
        while self._thread is not None:
            if not pygame.mixer.music.get_busy():
                self.talking = False
                self._playing = True
                if self.talking is not self.last_emitted_talking:
                    self.emitter.emit_expression("happy", self.talking)
                    self.last_emitted_talking = self.talking
                
                item = self._queue.get()
                play_mp3(item)
            else:
                time.sleep(0.05)
                if self.talking is not self.last_emitted_talking:
                    self.emitter.emit_expression("happy", self.talking)
                    self.last_emitted_talking = self.talking
                self.talking = not self.talking    
            time.sleep(0.05)  # 50 milliseconds delay

    def reset(self):
        self._thread = threading.Thread(target=self._play_audio)
        self._playing = False
        # Initialize pygame mixer
        pygame.mixer.init()
        self._thread.start()

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
    #speech_queue.join()
