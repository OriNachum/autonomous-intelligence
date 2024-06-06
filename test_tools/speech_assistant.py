import soundfile as sf
from vosk import Model, KaldiRecognizer
import json
import pyttsx3

class SpeechAssistant:
    def __init__(self, vosk_model_path="vosk-model", sample_rate=16000, tts_rate=150, tts_volume=0.9):
        # Initialize STT
        self.model = Model(vosk_model_path)
        self.recognizer = KaldiRecognizer(self.model, sample_rate)
        
        # Initialize TTS
        self.engine = pyttsx3.init()
        self.engine.setProperty('rate', tts_rate)
        self.engine.setProperty('volume', tts_volume)
    
    def speech_to_text(self, audio_file):
        with sf.SoundFile(audio_file) as f:
            audio_data = f.read(dtype='int16')
            self.recognizer.AcceptWaveform(audio_data.tobytes())
            result = self.recognizer.Result()
        result_dict = json.loads(result)
        return result_dict.get('text', '')
    
    def text_to_speech(self, text):
        self.engine.say(text)
        self.engine.runAndWait()
    
    def process_audio(self, audio_file):
        recognized_text = self.speech_to_text(audio_file)
        print("Recognized text:", recognized_text)
        
        response_text = "I heard you say: " + recognized_text
        self.text_to_speech(response_text)
        return recognized_text

if __name__ == "__main__":
    assistant = SpeechAssistant()
    audio_file = 'example_audio.wav'
    assistant.process_audio(audio_file)
