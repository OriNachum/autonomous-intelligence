import os
from pathlib import Path
import pygame
import time
from dotenv import load_dotenv
from openai import OpenAI

load_dotenv() 
client = OpenAI()

def speechify(text: str):
    speech_file_path = Path(__file__).parent / "speech.mp3"
    response = client.audio.speech.create(
        model="tts-1",
        voice="alloy",
        input=text
    )

    response.stream_to_file(speech_file_path)
    return speech_file_path

def play_mp3(path):
    # Initialize pygame mixer
    pygame.mixer.init()
    # Load the MP3 file
    pygame.mixer.music.load(path)
    # Play the MP3 file
    pygame.mixer.music.play()
    
    # Wait for the music to play. This is a simple way to keep the program running while the music plays.
    # In a more complex application, you wouldn't use time.sleep() but manage the playback status more gracefully.
    #while pygame.mixer.music.get_busy():
     #   time.sleep(1)



if __name__ == "__main__":
    path = speechify("Hello, World!")
    path = "speech.mp3"
    # Play the audio file, not using ffplay
    
    try:
      # Replace 'your_mp3_file.mp3' with the path to your MP3 file
      play_mp3('speech.mp3')
      input("Please confirm when the speech is done\ns")

    except:
      print("===== Error playing the audio file =====")
