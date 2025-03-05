import torch
import pyaudio
import numpy as np
import wave
import io
import time
import logging
from queue import Queue
from threading import Thread
import requests
import torchaudio

class SpeechTranscriber:
    def __init__(self, on_transcription=None, device='cuda', model_size="small", initial_prompt=None, parallel_callback_handling=True, stt_url="http://stt:8000/transcribe", vad_url="http://vad:8000/vad"):
        # Configure logging
        logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
        self.logger = logging.getLogger(__name__)
        
        # Initialize VAD model
        print(f"torch cuda is_available: {torch.cuda.is_available()}")
        self.device = torch.device(device)
        self.vad_model, _ = torch.hub.load(repo_or_dir='snakers4/silero-vad',
                                         model='silero_vad',
                                         force_reload=False)
        self.vad_model = self.vad_model.to(self.device)
        
        # Audio settings
        self.chunk_size = 512  # 512 for 16000 Hz
        self.rate = 16000
        self.p = pyaudio.PyAudio()
        self.input_device_index = self.get_input_device()
        
        # Speech detection settings
        self.threshold = 0.5
        self.speaking = False
        self.silence_duration = 0
        self.max_silence_duration = 2.0  # seconds
        
        # Recording state
        self.audio_buffer = []
        self.is_recording = False
        
        # Transcription settings
        self.initial_prompt = initial_prompt
        self.on_transcription = on_transcription
        self.parallel_callback_handling = parallel_callback_handling
        self.callback_running = False
        self.stt_url = stt_url
        self.vad_url = vad_url
        
    def get_input_device(self):
        """Find the index of the default input device."""
        for i in range(self.p.get_device_count()):
            device_info = self.p.get_device_info_by_index(i)
            if device_info['maxInputChannels'] > 0:
                self.logger.info(f"Found input device: {device_info['name']}")
                return i
        return None
        
    def transcribe_audio(self, audio_data):
        """Transcribe audio using STT API."""
        try:
            # Convert audio data to WAV format using torchaudio
            waveform = torch.from_numpy(np.frombuffer(audio_data, dtype=np.int16)).float()
            waveform = waveform.unsqueeze(0)  # Add channel dimension
            
            # Save as wav in memory
            wav_buffer = io.BytesIO()
            torchaudio.save(wav_buffer, waveform, self.rate, format="wav")
            wav_buffer.seek(0)
            
            files = {'audio_file': wav_buffer}
            response = requests.post(self.stt_url, files=files)
            response.raise_for_status()
            
            transcription = response.json().get('text', '')
            return transcription.strip()
        except requests.exceptions.RequestException as e:
            self.logger.error(f"Transcription error: {str(e)}")
            return ""
    
    def process_audio(self, in_data, frame_count, time_info, status):
        """Process audio data, detect speech, and trigger transcription."""
        try:
            # Convert byte data to tensor
            audio_data = np.frombuffer(in_data, dtype=np.int16)
            audio_tensor = torch.from_numpy(audio_data).float()
            audio_tensor = audio_tensor / 32768.0  # Normalize to [-1, 1]
            audio_tensor = audio_tensor.unsqueeze(0).to(self.device)
            
            # Get speech probability
            speech_prob = self.vad_model(audio_tensor, self.rate).item()
            
            if speech_prob > self.threshold:
                if not self.speaking:
                    self.logger.info("Speech detected - starting to record")
                    self.speaking = True
                    self.audio_buffer = []
                self.audio_buffer.append(in_data)
                self.silence_duration = 0
            else:
                if self.speaking:
                    self.silence_duration += len(audio_data) / self.rate
                    self.audio_buffer.append(in_data)
                    
                    if self.silence_duration > self.max_silence_duration:
                        self.logger.info("Speech ended - transcribing")
                        self.speaking = False
                        self.silence_duration = 0
                        
                        # Transcribe the collected audio
                        if self.audio_buffer:
                            transcription = self.transcribe_audio(self.audio_buffer)
                            if transcription and self.on_transcription:
                                if self.parallel_callback_handling or not self.callback_running:
                                    self.callback_running = True 
                                    self.on_transcription(transcription)
                                    self.callback_running = False
                            self.audio_buffer = []
            
            return (in_data, pyaudio.paContinue)
        except Exception as e:
            self.logger.error(f"Error in process_audio: {str(e)}")
            return (None, pyaudio.paAbort)
    
    def start(self):
        """Start recording and transcribing speech."""
        try:
            self.is_recording = True
            
            # Open audio stream
            stream = self.p.open(format=pyaudio.paInt16,
                               channels=1,
                               rate=self.rate,
                               input=True,
                               frames_per_buffer=self.chunk_size,
                               input_device_index=self.input_device_index,
                               stream_callback=self.process_audio)
            
            self.logger.info("Started recording. Speak to test...")
            
            # Keep the stream open
            while self.is_recording and stream.is_active():
                time.sleep(0.1)
                
        except Exception as e:
            self.logger.error(f"Error: {str(e)}")
        finally:
            self.stop(stream if 'stream' in locals() else None)
    
    def stop(self, stream=None):
        """Stop recording and clean up resources."""
        self.is_recording = False
        if stream:
            stream.stop_stream()
            stream.close()
        self.p.terminate()
        self.logger.info("Recording stopped and resources cleaned up")


def main():
    """Example usage with callback."""
    def handle_transcription(text):
        print(f"\nTranscription received: {text}\n")
        print("Listening for more speech...")
    
    # Create transcriber with callback
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
