import torch
import sounddevice as sd
import numpy as np
import wave
import io
import time
import logging
from queue import Queue
from threading import Thread
from faster_whisper import WhisperModel
import onnxruntime as ort

class SpeechTranscriber:
    def __init__(self, on_transcription=None, device='cuda', model_size="small", initial_prompt=None, parallel_callback_handling=True):
        logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
        self.logger = logging.getLogger(__name__)
        
        # Initialize models
        print(f"torch cuda is_available: {torch.cuda.is_available()}")
        self.device = torch.device(device)
        self.vad_model, _ = torch.hub.load(repo_or_dir='snakers4/silero-vad',
                                         model='silero_vad',
                                         force_reload=False)
        self.vad_model = self.vad_model.to(self.device)
        
        self.logger.info("ONNX Available providers:", ort.get_available_providers())
        self.logger.info("Loading Whisper model...")
        self.whisper_model = WhisperModel(model_size, device=device, compute_type="int8")
        self.logger.info("Whisper model loaded successfully")
        
        # Audio settings
        self.chunk_size = 512
        self.rate = 16000
        self.channels = 1
        
        # Speech detection settings
        self.threshold = 0.5
        self.speaking = False
        self.silence_duration = 0
        self.max_silence_duration = 2.0
        
        # Recording state
        self.audio_buffer = []
        self.is_recording = False
        
        # Transcription settings
        self.initial_prompt = initial_prompt
        self.on_transcription = on_transcription
        self.parallel_callback_handling = parallel_callback_handling
        self.callback_running = False
        
    def transcribe_audio(self, audio_data):
        try:
            wav_buffer = io.BytesIO()
            with wave.open(wav_buffer, 'wb') as wf:
                wf.setnchannels(1)
                wf.setsampwidth(2)
                wf.setframerate(self.rate)
                wf.writeframes(b''.join(audio_data))
            wav_buffer.seek(0)
            
            segments, info = self.whisper_model.transcribe(
                wav_buffer,
                beam_size=5,
                initial_prompt=self.initial_prompt,
                language='en',
                condition_on_previous_text=True
            )
            
            transcription = ""
            for segment in segments:
                transcription += f"{segment.text}\n"
            
            return transcription.strip()
        except Exception as e:
            self.logger.error(f"Transcription error: {str(e)}")
            return ""
    
    def process_audio(self, indata, frames, time, status):
        if status:
            self.logger.warning(status)
        
        try:
            audio_data = indata.flatten()
            audio_tensor = torch.from_numpy(audio_data).float()
            audio_tensor = audio_tensor.unsqueeze(0).to(self.device)
            
            speech_prob = self.vad_model(audio_tensor, self.rate).item()
            
            if speech_prob > self.threshold:
                if not self.speaking:
                    self.logger.info("Speech detected - starting to record")
                    self.speaking = True
                    self.audio_buffer = []
                self.audio_buffer.append(audio_data.tobytes())
                self.silence_duration = 0
            else:
                if self.speaking:
                    self.silence_duration += len(audio_data) / self.rate
                    self.audio_buffer.append(audio_data.tobytes())
                    
                    if self.silence_duration > self.max_silence_duration:
                        self.logger.info("Speech ended - transcribing")
                        self.speaking = False
                        self.silence_duration = 0
                        
                        if self.audio_buffer:
                            transcription = self.transcribe_audio(self.audio_buffer)
                            if transcription and self.on_transcription:
                                if self.parallel_callback_handling or not self.callback_running:
                                    self.callback_running = True 
                                    self.on_transcription(transcription)
                                    self.callback_running = False
                            self.audio_buffer = []
        
        except Exception as e:
            self.logger.error(f"Error in process_audio: {str(e)}")
    
    def start(self):
        try:
            self.is_recording = True
            
            with sd.InputStream(channels=self.channels,
                              samplerate=self.rate,
                              blocksize=self.chunk_size,
                              callback=self.process_audio,
                              dtype=np.float32):
                
                self.logger.info("Started recording. Speak to test...")
                
                while self.is_recording:
                    time.sleep(0.1)
                    
        except Exception as e:
            self.logger.error(f"Error: {str(e)}")
        finally:
            self.stop()
    
    def stop(self):
        self.is_recording = False
        self.logger.info("Recording stopped")

def main():
    def handle_transcription(text):
        print(f"\nTranscription received: {text}\n")
        print("Listening for more speech...")
    
    transcriber = SpeechTranscriber(
        on_transcription=handle_transcription,
        initial_prompt="The following is a clear and accurate transcription of speech:",
        model_size="small",
        device="cuda"
    )
    
    try:
        print("Starting transcriber. Speak to test (Ctrl+C to exit)...")
        transcriber.start()
    except KeyboardInterrupt:
        print("\nStopping...")
    finally:
        transcriber.stop()

if __name__ == "__main__":
    main()