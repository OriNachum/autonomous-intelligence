import soundfile as sf
from vosk import Model, KaldiRecognizer
import json
import pyttsx3
import pyaudio  # Added for real-time audio
import threading  # Added for handling streaming in a separate thread

class SpeechAssistant:
    def __init__(self, vosk_model_path="vosk-model", sample_rate=16000, tts_rate=150, tts_volume=0.9):
        # Initialize STT
        self.model = Model(vosk_model_path)
        self.recognizer = KaldiRecognizer(self.model, sample_rate)
        
        # Initialize TTS
        self.engine = pyttsx3.init()
        self.engine.setProperty('rate', tts_rate)
        self.engine.setProperty('volume', tts_volume)
        
        self.sample_rate = sample_rate
        self.audio = pyaudio.PyAudio()  # Initialize PyAudio
        self.stream = self.audio.open(format=pyaudio.paInt16,
                                      channels=1,
                                      rate=self.sample_rate,
                                      input=True,
                                      frames_per_buffer=8000)
        self.stream.start_stream()
        self.chunk_size = 8000
        self.buffer_size = 32000
    
    def speech_to_text(self, audio_file):
        with sf.SoundFile(audio_file) as f:
            audio_data = f.read(dtype='int16')
            self.recognizer.AcceptWaveform(audio_data.tobytes())
            result = self.recognizer.Result()
        result_dict = json.loads(result)
        return result_dict.get('text', '')
    
    def speech_to_text_real_time(self):
        buffer = b''
        silence_threshold = 500  # Adjust based on your mic
        
        while True:
            data = self.stream.read(self.chunk_size, exception_on_overflow=False)
            if max(abs(int.from_bytes(data[i:i+2], 'little', signed=True)) for i in range(0, len(data), 2)) > silence_threshold:
                buffer += data
                
            if len(buffer) >= self.buffer_size:
                if self.recognizer.AcceptWaveform(buffer):
                    result = json.loads(self.recognizer.Result())
                    text = result.get('text', '').strip()
                    if text:
                        print("Recognized text:", text)
                        response_text = "I heard you say: " + text
                        self.text_to_speech(response_text)
                buffer = buffer[16000:]  # Sliding window with overlap
    
    def text_to_speech(self, text):
        self.engine.say(text)
        self.engine.runAndWait()
    
    def process_audio(self, audio_file):
        recognized_text = self.speech_to_text(audio_file)
        print("Recognized text:", recognized_text)
        
        response_text = "I heard you say: " + recognized_text
        self.text_to_speech(response_text)
        return recognized_text
    
    def process_audio_real_time(self):
        threading.Thread(target=self.speech_to_text_real_time).start()

if __name__ == "__main__":
    assistant = SpeechAssistant()
    assistant.process_audio_real_time()
    # Keep the main thread alive
    try:
        while True:
            pass
    except KeyboardInterrupt:
        pass
