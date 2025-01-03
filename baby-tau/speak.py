import subprocess
import threading   

# echo 'Welcome to the world of speech synthesis!' | piper --model en_US-lessac-medium   --output_raw | aplay -f S16_LE -c1 -r16000
def speak_piper(text):
    try:
        # Run piper with the specified language and text
        subprocess.run(["echo", text, "|", "piper", "--model", "en_US-lessac-medium", "--output_raw", "|", "aplay", "-f", "S16_LE", "-c1", "-r16000"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except Exception as e:
        print(f"Error speaking: {e}")

def speak_espeak(text):
    try:
        # Run espeakng with the specified language and text
        subprocess.run(["espeak", "-v", "en-us", text], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except Exception as e:
        print(f"Error speaking: {e}")


def speak_async(text):
    # Use a new thread to run espeakng in the background

    # Create a new thread to run espeakng
    threading.Thread(target=speak_espeak, args=(text,)).start()

