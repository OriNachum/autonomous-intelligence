import torch
import numpy as np
import pyaudio
import logging
import requests
import io
import torchaudio

class SpeechDetector:
    def __init__(self, device='cuda', vad_url="http://vad:8000/vad"):
        # Configure logging
        logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - SpeechDetector - %(message)s')
        self.logger = logging.getLogger(__name__)
        
        # Audio settings
        self.chunk_size = 512  # 512 for 16000 Hz
        self.rate = 16000
        self.p = pyaudio.PyAudio()
        self.input_device_index = self.get_input_device()
        
        # Speech detection settings
        self.threshold = 0.5
        self.speaking = False
        self.audio_buffer = []
        self.vad_url = vad_url
        self.device = device
        
    def get_input_device(self):
        """Find the index of the default input device."""
        for i in range(self.p.get_device_count()):
            device_info = self.p.get_device_info_by_index(i)
            if device_info['maxInputChannels'] > 0:
                self.logger.info(f"Found input device: {device_info['name']}")
                return i
        return None
        
    def record(self, timeout=10.0):
        """Record audio until speech is detected or timeout is reached."""
        try:
            self.logger.info("Starting recording...")
            stream = self.p.open(format=pyaudio.paInt16,
                               channels=1,
                               rate=self.rate,
                               input=True,
                               frames_per_buffer=self.chunk_size,
                               input_device_index=self.input_device_index)
            
            start_time = time.time()
            self.speaking = False
            self.audio_buffer = []
            
            while time.time() - start_time < timeout:
                in_data = stream.read(self.chunk_size, exception_on_overflow=False)
                # Convert audio data to WAV format using torchaudio
                waveform = torch.from_numpy(np.frombuffer(in_data, dtype=np.int16)).float()
                waveform = waveform.unsqueeze(0)  # Add channel dimension
                
                # Save as wav in memory
                buffer = io.BytesIO()
                torchaudio.save(buffer, waveform, self.rate, format="wav")
                buffer.seek(0)
                
                files = {'audio_file': buffer}
                response = requests.post(self.vad_url, files=files)
                response.raise_for_status()
                
                speech_prob = response.json().get('speech_probability', 0.0)
                
                if speech_prob > self.threshold:
                    self.logger.info("Speech detected - recording")
                    self.speaking = True
                    self.audio_buffer.append(in_data)
                elif self.speaking:
                    self.logger.info("Speech ended - stopping recording")
                    break
                else:
                    self.audio_buffer.append(in_data)
            
            stream.stop_stream()
            stream.close()
            
            if self.audio_buffer:
                return b''.join(self.audio_buffer)
            else:
                return None
        except Exception as e:
            self.logger.error(f"Error during recording: {str(e)}")
            return None
    
    def close(self):
        """Clean up resources."""
        self.p.terminate()
        self.logger.info("Resources cleaned up")

if __name__ == '__main__':
    import time
    
    detector = SpeechDetector()
    try:
        print("Starting speech detection. Speak to test (Ctrl+C to exit)...")
        audio_data = detector.record()
        if audio_data:
            print("Speech recorded successfully")
        else:
            print("No speech detected")
    except KeyboardInterrupt:
        print("\nStopping...")
    finally:
        detector.close()
