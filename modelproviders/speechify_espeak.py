import subprocess
from pathlib import Path
import re

class SpeechService:
    def speechify(self, text: str, path: str):
        text_in_quotes = re.findall(r'\"(.+?)\"', text)
        if len(text_in_quotes) == 0:
            return None
        text = "\n\n".join(text_in_quotes)

        speech_file_path = Path(path)
        speech_file_path.parent.mkdir(parents=True, exist_ok=True)

        try:
            # Use espeak to synthesize speech and save to WAV file
            subprocess.run(['espeak', '-w', str(speech_file_path), text], check=True)
            return speech_file_path
        except subprocess.CalledProcessError as e:
            print(f"Espeak failed: {e}")
            return None

    def play_mp3(self, path):
        pygame.mixer.init()
        pygame.mixer.music.load(path)
        pygame.mixer.music.play()

if __name__ == "__main__":
    service = SpeechService()
    sample_text = 'Hello, "This should be spoken." And this should not be.'
    output_path = "output.wav"
    result = service.speechify(sample_text, output_path)
    if result:
        print(f"Speech file created at: {result}")
    else:
        print("Speech generation failed.")