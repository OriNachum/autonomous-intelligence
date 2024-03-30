import os
import re
from pathlib import Path
import pygame
import requests
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
OPENAI_API_URL = "https://api.openai.com/v1/audio/speech"

if not OPENAI_API_KEY:
    raise ValueError("OPENAI_API_KEY environment variable is not set.")

HEADERS = {
    "Authorization": f"Bearer {OPENAI_API_KEY}",
    "Content-Type": "application/json"
}

def speechify(text: str):
    # Extract from the text only " quotations. Drop to double new line between quotes.
    text_in_quotes = re.findall(r'\"(.+?)\"', text)
    if len(text_in_quotes) == 0:
        return None
    text = "\n\n".join(text_in_quotes)
    print(text)

    payload = {
        "model": "tts-1",
        "voice": "alloy",
        "input": text
    }

    response = requests.post(OPENAI_API_URL, json=payload, headers=HEADERS)
    if response.status_code != 200:
        raise Exception(f"API request failed with status code {response.status_code}: {response.text}")

    speech_file_path = Path(__file__).parent / "speech.mp3"
    with open(speech_file_path, 'wb') as f:
        f.write(response.content)

    return speech_file_path

def play_mp3(path):
    pygame.mixer.init()
    pygame.mixer.music.load(path)
    pygame.mixer.music.play()

    # Using time.sleep() in a real application isn't the best practice for handling audio playback.
    # You'd typically check the playback status in a more interactive or event-driven way.

if __name__ == "__main__":
    path = speechify("Hello, World! \"This is a test\". This should not be spoken. \"This is another test\". And here is another test.")
    if path:
        try:
            play_mp3(path)
            input("Press Enter after the speech is done.\n")
        except Exception as e:
            print("===== Error playing the audio file =====")
            print(e)
    else:
        print("No speech generated.")
