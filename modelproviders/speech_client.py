
from speechify_espeak import SpeechService
from openai_api_client import OpenAIService

class SpeechClient:
    def __init__(self, provider: str):
        if provider.lower() == 'openai':
            self.service = OpenAIService()
        elif provider.lower() == 'speechify':
            self.service = SpeechService()
        else:
            raise ValueError(f"Unsupported provider: {provider}")

    def speechify(self, text: str, path: str):
        return self.service.speechify(text, path)

    def play_mp3(self, path: str):
        self.service.play_mp3(path)