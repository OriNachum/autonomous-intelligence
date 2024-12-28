import subprocess

class TextToSpeechAssistant:
    
    def text_to_speech(self, text):
        # Construct the eSpeak command
        command = ['espeak', f'-a 10 -p 99 -s 200 -v en-us+m2', text]
        subprocess.call(command)

    def run(self):
        # Example text
        text = "Hello, how can I assist you today?"
        print(f"Speaking: {text}")
        self.text_to_speech(text)

if __name__ == "__main__":
    assistant = TextToSpeechAssistant()
    assistant.run()
