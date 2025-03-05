import requests
import logging

logger = logging.getLogger(__name__)

class Speaker:
    def __init__(self, tts_url="http://kokoroTTS:8000/speak"):
        self.tts_url = tts_url
        self.logger = logging.getLogger(__name__)

    def speak(self, text):
        """Call the TTS service to speak the given text."""
        try:
            response = requests.post(self.tts_url, json={"text": text})
            response.raise_for_status()  # Raise HTTPError for bad responses (4xx or 5xx)
            self.logger.info("TTS request successful")
        except requests.exceptions.RequestException as e:
            self.logger.error(f"Error calling TTS service: {e}")

if __name__ == '__main__':
    # Example Usage
    speaker = Speaker()
    speaker.speak("Hello, this is a test message.")
