import os
import re
from pathlib import Path
import pygame
import requests
import json
from dotenv import load_dotenv

class OpenAIService:
    def __init__(self):
        load_dotenv()
        self.api_key = os.getenv("OPENAI_API_KEY")
        self.api_url = "https://api.openai.com/v1"
        self.audio_url = f"{self.api_url}/audio/speech"
        self.headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }

        if not self.api_key:
            raise ValueError("OPENAI_API_KEY environment variable is not set.")

    def speechify(self, text: str, path: str):
        text_in_quotes = re.findall(r'\"(.+?)\"', text)
        if len(text_in_quotes) == 0:
            return None
        text = "\n\n".join(text_in_quotes)

        payload = {
            "model": "tts-1",
            "voice": "alloy",
            "input": text
        }

        response = requests.post(self.audio_url, json=payload, headers=self.headers)
        if response.status_code != 200:
            message = f"API request failed with status code {response.status_code}: {response.text}"
            print(message)
            raise Exception(message)

        speech_file_path = Path(__file__).parent / path
        with open(speech_file_path, 'wb') as f:
            f.write(response.content)

        return speech_file_path

    def play_mp3(self, path):
        pygame.mixer.init()
        pygame.mixer.music.load(path)
        pygame.mixer.music.play()

    def get_model_id_by_name(self, model_name):
        model_map = {
            "gpt-3.5-turbo": "gpt-3.5-turbo",
            "gpt-4": "gpt-4o",
            "gpt-4o": "gpt-4o"
        }
        return model_map.get(model_name, "gpt-3.5-turbo")

    def parse_event(self, event):        
        event_str = event.decode('utf-8')
        #print(event_str)
        if event_str.endswith("[DONE]"):
            return "", None, None
        elif event_str.startswith("data: "):
            event_str = event_str[6:]
            try:
                object_response = json.loads(event_str)
                first_choice = object_response["choices"][0]
                if first_choice["finish_reason"] is None:
                    delta = first_choice["delta"]
                    content = delta["content"] if "content" in delta.keys() else ""
                    return content, first_choice, object_response 
                else:
                    return "", None, None
            except:
                print(f"ERROR {event_str}")
                return "", None, None
        else:
            return "", None, None

    def generate_stream_response(self, prompt, history, system_prompt, model, max_tokens=200):
        model_id = self.get_model_id_by_name(model)
        messages = [{"role": "system", "content": system_prompt}] if system_prompt else []
        
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
            response = session.post(f"{self.api_url}/chat/completions", json=payload, headers=self.headers, stream=True)
            
            for event in response.iter_lines():
                if event:
                    text, event_type, event_obj = self.parse_event(event)
                    #print(len(event_object), end='', flush=True)
                    yield text, event_type, event_obj
    
    def generate_response(self, prompt, history, system_prompt, model, max_tokens=200):
        model_id = self.get_model_id_by_name(model)
        messages = [{"role": "system", "content": system_prompt}] if system_prompt else []
        
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
            "max_tokens": max_tokens
        }

        response = requests.post(f"{self.api_url}/chat/completions", json=payload, headers=self.headers)
        if response.status_code != 200:
            raise Exception(f"API request failed with status code {response.status_code}: {response.text}")
        
        object_response = response.json()
        content = object_response['choices'][0]['message']['content']
        return content

if __name__ == "__main__":
    service = OpenAIService()
    mode = input("Enter mode ('text', 'stream' or 'speech'): ").strip().lower()

    if mode == "text":
        prompt = "Can you explain the theory of relativity?"
        history = "[User]: Hello\n[Assistant]: Hi! How can I help you today?"
        system_prompt = "You are a helpful assistant."
        model = "gpt-3.5-turbo"
        max_tokens = 150
        response = service.generate_response(prompt, history, system_prompt, model, max_tokens)
        print(response)
    elif mode == "stream":
        prompt = "Can you explain the theory of relativity?"
        history = "[User]: Hello\n[Assistant]: Hi! How can I help you today?"
        system_prompt = "You are a helpful assistant."
        model = "gpt-3.5-turbo"
        max_tokens = 150

        for response in service.generate_stream_response(prompt, history, system_prompt, model, max_tokens):
            if response is not None:
                    print(response, end='', flush=True)

    elif mode == "speech":
        path_input = "test.mp3"
        path = service.speechify("Hello, World! \"This is a test\". This should not be spoken. \"This is another test\". And here is another test. \"The quick brown fox jumps over the lazy dog, a phrase known for using every letter in the alphabet, perfectly illustrates how this is a test line I am now writing to show how text is being spoken. As the fox gracefully leaps over the dozing canine, it wonders if it might have a future in gymnastics, perhaps even the Olympics. Meanwhile, the dog, who had just settled in for a nice nap, dreams of finally catching that elusive squirrel that taunts him from the trees every day. Little does the fox know, the dog is secretly a master of martial arts, having trained in the ancient art of Taekwon-dog. This test line seamlessly integrates into the narrative, demonstrating not just how text can be spoken but also adding a humorous twist to a classic tale.\" ", path_input)
        if path:
            try:
                service.play_mp3(path)
                input("Press Enter after the speech is done.\n")
            except Exception as e:
                print("===== Error playing the audio file =====")
                print(e)
        else:
            print("No speech generated.")
    else:
        print("Invalid mode. Please enter 'text' or 'speech'.")
