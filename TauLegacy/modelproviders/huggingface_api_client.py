import os
import re
from pathlib import Path
import requests
import json
import io
import numpy as np

from dotenv import load_dotenv
from huggingface_hub import InferenceClient

class HuggingFaceService:
    def __init__(self):
        load_dotenv()
        self.api_key = os.getenv("HUGGINGFACE_API_KEY")
        self.api_url = "https://api-inference.huggingface.co/models/meta-llama/Llama-3.2-3B"
        self.headers = {
            "Authorization": f"Bearer {self.api_key}"
        }

        if not self.api_key:
            raise ValueError("HUGGINGFACE_API_KEY environment variable is not set.")

    def get_model_id_by_name(self, model_name):
        model_map = {
            "llama-3.2-3b": "meta-llama/Llama-3.2-3B",
            # Add other model mappings if necessary
        }
        return model_map.get(model_name, "meta-llama/Llama-3.2-3B")

    def generate_response(self, prompt, history, system_prompt, model, max_tokens=200):
        model_id = self.get_model_id_by_name(model)
        payload = {
            "inputs": prompt,
            "parameters": {
                "max_new_tokens": max_tokens
            }
        }

        response = requests.post(self.api_url, headers=self.headers, json=payload)
        if response.status_code != 200:
            raise Exception(f"API request failed with status code {response.status_code}: {response.text}")
        
        output = response.json()
        return output.get('generated_text', '')

    def generate_stream_response(self, prompt, history, system_prompt, model, max_tokens=200):
        model_id = self.get_model_id_by_name(model)
        client = InferenceClient(api_key=self.api_key)

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

        stream = client.chat.completions.create(
            model=model_id,
            messages=messages,
            max_tokens=max_tokens,
            stream=True
        )

        for chunk in stream:
            content = chunk.choices[0].delta.get("content", "")
            print(content, end="", flush=True)
            yield content, chunk.choices[0], chunk

    def transcribe_audio(self, audio_data, rate=16000):
        # ...existing code...
        # Modify transcription method if HuggingFace offers audio transcription
        pass

    # ...existing code...

if __name__ == "__main__":
    service = HuggingFaceService()
    prompt = "What is the capital of France?"
    response = service.generate_response(
        prompt=prompt,
        history="",
        system_prompt="You are a knowledgeable assistant.",
        model="llama-3.2-3b",
        max_tokens=50
    )
    print(f"Response: {response}")