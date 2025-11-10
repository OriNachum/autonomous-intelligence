import torch
import pyaudio
import numpy as np
import time
from queue import Queue
from threading import Thread

class SpeechDetector:
    def __init__(self, device='cpu'):
        self.device = torch.device(device)
        self.model, utils = torch.hub.load(repo_or_dir='snakers4/silero-vad',
                                         model='silero_vad',
                                         force_reload=False)
        self.model = self.model.to(self.device)
        
        # Audio settings
        self.chunk_size = 512 #1024 not supported. 256 for 8000, 512 for 16000
        self.rate = 16000
        self.p = pyaudio.PyAudio()
        self.input_device_index = self.get_input_device()
        self.transcription_queue = Queue()
        
        # VAD settings
        self.threshold = 0.5
        self.min_speech_duration = 0.5
        self.speaking = False
        self.silence_duration = 0
        self.max_silence_duration = 1.0  # seconds
        
    def get_input_device(self):
        """Find the index of the default input device."""
        for i in range(self.p.get_device_count()):
            device_info = self.p.get_device_info_by_index(i)
            if device_info['maxInputChannels'] > 0:
                print(f"Found input device: {device_info['name']}")
                return i
        return None

    def get_speech_timestamps(self, audio_tensor, model, sampling_rate=16000):
        """Get speech timestamps from audio tensor using Silero VAD."""
        return model(audio_tensor, sampling_rate).tolist()

    def process_audio(self, in_data, frame_count, time_info, status):
        """Process audio data and detect speech."""
        try:
            # Convert byte data to tensor
            audio_data = np.frombuffer(in_data, dtype=np.int16)
            audio_tensor = torch.from_numpy(audio_data).float()
            audio_tensor = audio_tensor / 32768.0  # Normalize to [-1, 1]
            audio_tensor = audio_tensor.unsqueeze(0).to(self.device)

            # Get speech probability
            speech_prob = self.model(audio_tensor, self.rate).item()
            
            if speech_prob > self.threshold:
                if not self.speaking:
                    print("Speech detected!")
                    self.speaking = True
                self.silence_duration = 0
            else:
                if self.speaking:
                    self.silence_duration += len(audio_data) / self.rate
                    if self.silence_duration > self.max_silence_duration:
                        print("Speech ended.")
                        self.speaking = False
                        self.silence_duration = 0

            return (in_data, pyaudio.paContinue)
        except Exception as e:
            print(f"Error in process_audio: {str(e)}")
            return (None, pyaudio.paAbort)

    def start_recording(self):
        """Start recording and detecting speech."""
        try:
            # Open audio stream
            stream = self.p.open(format=pyaudio.paInt16,
                               channels=1,
                               rate=self.rate,
                               input=True,
                               frames_per_buffer=self.chunk_size,
                               input_device_index=self.input_device_index,
                               stream_callback=self.process_audio)

            print("Recording started. Speak to test...")
            
            # Keep the stream open
            while stream.is_active():
                time.sleep(0.1)

        except KeyboardInterrupt:
            print("\nStopping...")
        except Exception as e:
            print(f"Error: {str(e)}")
        finally:
            if 'stream' in locals():
                stream.stop_stream()
                stream.close()
            self.p.terminate()

# Usage example
if __name__ == "__main__":
    detector = SpeechDetector()
    detector.start_recording()
