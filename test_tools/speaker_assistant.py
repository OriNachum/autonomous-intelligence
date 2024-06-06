import subprocess

class TextToSpeechAssistant:
    def __init__(self, tts_rate=150, tts_volume=100):
        self.tts_rate = tts_rate
        self.tts_volume = tts_volume
    
    def text_to_speech(self, text):
        # Construct the eSpeak command
        command = ['espeak', f'-s {self.tts_rate}', f'-a {self.tts_volume}', text]
        subprocess.call(command)
    
    def run(self):
        # Example text
        text = "Hello, how can I assist you today?"
        print(f"Speaking: {text}")
        self.text_to_speech(text)

if __name__ == "__main__":
    assistant = TextToSpeechAssistant()
    assistant.run()
