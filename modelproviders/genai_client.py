
from openai_api_client import OpenAIService
from huggingface_api_client import HuggingFaceService
from google_api_client import GoogleGenerativeAIClient

class GenAIClient:
    def __init__(self):
        self.clients = {
            "gpt-3.5-turbo": OpenAIService(),
            "gpt-4o": OpenAIService(),
            "llama-3.2-3b": HuggingFaceService(),
            "gemini-2.0-flash-exp": GoogleGenerativeAIClient()
        }

    def get_client(self, model):
        client = self.clients.get(model)
        if not client:
            raise ValueError(f"No client found for model: {model}")
        return client

    def generate_response(self, prompt, history, system_prompt, model, max_tokens=200):
        client = self.get_client(model)
        return client.generate_response(prompt, history, system_prompt, model, max_tokens)

    def generate_stream_response(self, prompt, history, system_prompt, model, max_tokens=200):
        client = self.get_client(model)
        return client.generate_stream_response(prompt, history, system_prompt, model, max_tokens)

    def transcribe_audio(self, audio_data, rate=16000, model=None):
        client = self.get_client(model)
        return client.transcribe_audio(audio_data, rate)