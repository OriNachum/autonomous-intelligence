import os
import re
from pathlib import Path
import pygame
import requests
import json
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
API_URL = "https://api.openai.com/v1"
OPENAI_API_URL = f"{API_URL}/audio/speech"

if not OPENAI_API_KEY:
    raise ValueError("OPENAI_API_KEY environment variable is not set.")

HEADERS = {
    "Authorization": f"Bearer {OPENAI_API_KEY}",
    "Content-Type": "application/json"
}

def speechify(text: str, path: str):
    # Extract from the text only " quotations. Drop to double new line between quotes.
    text_in_quotes = re.findall(r'\"(.+?)\"', text)
    if len(text_in_quotes) == 0:
        return None
    text = "\n\n".join(text_in_quotes)
    #print(text)

    payload = {
        "model": "tts-1",
        "voice": "alloy",
        "input": text
    }

    response = requests.post(OPENAI_API_URL, json=payload, headers=HEADERS)
    if response.status_code != 200:
        message=f"API request failed with status code {response.status_code}: {response.text}"
        print(message)
        raise Exception(message)

    speech_file_path = Path(__file__).parent / path
    with open(speech_file_path, 'wb') as f:
        f.write(response.content)

    return speech_file_path

def play_mp3(path):
    pygame.mixer.init()
    pygame.mixer.music.load(path)
    pygame.mixer.music.play()

    # Using time.sleep() in a real application isn't the best practice for handling audio playback.
    # You'd typically check the playback status in a more interactive or event-driven way.

def get_model_id_by_name(model_name):
    model_map = {
        "gpt-3.5-turbo": "gpt-3.5-turbo",
        "gpt-4": "gpt-4"
    }
    return model_map.get(model_name, "gpt-3.5-turbo")

def parse_event(event):
    # Example event parsing logic (adjust as needed)
    event_str = event.decode('utf-8')
    # Remove the first occurrence of "data: "
    if event_str.endswith("[DONE]"):
        return None
    elif event_str.startswith("data: "):
        event_str = event_str[6:]
        try:
            return json.loads(event_str)
        except:
            print(f"ERROR {event_str}")
            return None
    else:
        return None

def generate_stream_response(prompt, history, system_prompt, model, max_tokens=200):
    model_id = get_model_id_by_name(model)
    if system_prompt is not None and system_prompt != "":
        messages = [{"role": "system", "content": system_prompt}]
    else:
        messages = []
        
    if history:
        for entry in history.split("\n"):
            if "[User]" in entry:
                user_message = entry.split("[User]: ")[1]
                messages.append({"role": "user", "content": user_message})
            elif "[Assistant]" in entry:
                assistant_message = entry.split("[Assistant]: ")[1]
                messages.append({"role": "assistant", "content": assistant_message})
    
    messages.append({"role": "user", "content": prompt})

    payload = {
        "model": model_id,
        "messages": messages,
        "max_tokens": max_tokens,
        "stream": True
    }

    with requests.Session() as session:
        response = session.post(f"{API_URL}/chat/completions", json=payload, headers=HEADERS, stream=True)
        
        for event in response.iter_lines():
            if event:
                event_object = parse_event(event)
                yield event_object


if __name__ == "__main__":
    mode = input("Enter mode ('text' or 'speech'): ").strip().lower()

    if mode == "text":
        prompt = "Can you explain the theory of relativity?"
        history = "[User]: Hello\n[Assistant]: Hi! How can I help you today?"
        system_prompt = "You are a helpful assistant."
        model = "gpt-3.5-turbo"
        max_tokens = 150

        # Generate and print stream responses
        for response in generate_stream_response(prompt, history, system_prompt, model, max_tokens):
            if response is not None:
                first_choice = response["choices"][0]
                if first_choice["finish_reason"] is None:
                    delta = response["choices"][0]["delta"]
                    print(delta["content"], end='', flush=True)

    elif mode == "speech":
        path_input = "test.mp3"
        path = speechify("Hello, World! \"This is a test\". This should not be spoken. \"This is another test\". And here is another test.", path_input)
        if path:
            try:
                play_mp3(path)
                input("Press Enter after the speech is done.\n")
            except Exception as e:
                print("===== Error playing the audio file =====")
                print(e)
        else:
            print("No speech generated.")
    else:
        print("Invalid mode. Please enter 'text' or 'speech'.")
