import subprocess
import threading   

def speak(text):
    # Use a new thread to run espeakng in the background
    def espeak_thread():
        try:
            # Run espeakng with the specified language and text
            subprocess.run(["espeak", "-v", "en-us", 
text], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except Exception as e:
            print(f"Error speaking: {e}")

    # Create a new thread to run espeakng
    threading.Thread(target=espeak_thread).start()

