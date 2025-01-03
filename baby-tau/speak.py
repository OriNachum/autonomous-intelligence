import subprocess
import threading   

class Speaker:
    def __init__(self):
        # Initialize models if needed
        pass  # No persistent models to load for subprocess-based speech

    def speak_piper(self, text):
        try:
            echo = subprocess.Popen(['echo', text], stdout=subprocess.PIPE)
            piper = subprocess.Popen(['piper', '--model', 'en_US-lessac-high', '--output_raw'], 
                                   stdin=echo.stdout,
                                   stdout=subprocess.PIPE)
            aplay = subprocess.Popen(['aplay', '-f', 'S16_LE', '-c1', '-r22050'],
                                   stdin=piper.stdout)
            aplay.wait()
        except Exception as e:
            print(f"Error speaking: {e}")

    def speak_espeak(self, text):
        try:
            # Run espeakng with the specified language and text
            subprocess.run(["espeak", "-v", "en-us", text], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except Exception as e:
            print(f"Error speaking: {e}")

    def speak_async(self, text):
        # Use a new thread to run espeakng in the background
        threading.Thread(target=self.speak_espeak, args=(text,)).start()

