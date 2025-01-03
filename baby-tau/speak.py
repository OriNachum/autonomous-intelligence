import subprocess
import threading   

def speak(text):
    try:
        # Run espeakng with the specified language and text
        subprocess.run(["espeak", "-v", "en-us", text], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except Exception as e:
        print(f"Error speaking: {e}")


def speak_async(text):
    # Use a new thread to run espeakng in the background

    # Create a new thread to run espeakng
    threading.Thread(target=speak, args=(text,)).start()

