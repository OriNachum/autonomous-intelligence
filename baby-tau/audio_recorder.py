import pyaudio
import wave
import logging
import os
from dotenv import load_dotenv
from transcribe_audio import Transcriber  # New import

# Load environment variables
load_dotenv()

# Set up logging
logging.basicConfig(level=logging.DEBUG, format='%(asctime)s %(levelname)s: %(message)s')

class AudioRecorder:
    def __init__(self, rate=16000, frame_duration=20, record_seconds=10, output_filename="output.wav"):
        self.rate = rate
        self.frame_duration = frame_duration  # Duration of a frame in milliseconds
        self.chunk_size = int(rate * frame_duration / 1000)  # Number of frames per buffer
        self.record_seconds = record_seconds
        self.output_filename = output_filename
        self.p = pyaudio.PyAudio()
        # Initialize Transcriber
        self.transcriber = Transcriber()
        self.device_name = os.getenv('AUDIO_DEVICE_NAME', 'default').lower()

    def find_input_device(self):
        device_count = self.p.get_device_count()
        for i in range(device_count):
            device_info = self.p.get_device_info_by_index(i)
            if self.device_name in device_info['name'].lower():
                logging.info(f"Found matching device: {device_info['name']} (index {i})")
            
                self.input_device_index = i
                return i
        logging.warning("Suitable input device not found")
        return None

    def record(self):
        # Open audio stream
        stream = self.p.open(format=pyaudio.paInt16, channels=1, rate=self.rate,
                             input=True, frames_per_buffer=self.chunk_size, input_device_index=self.input_device_index)

        print("Recording...")

        frames = []
        for _ in range(0, int(self.rate / self.chunk_size * self.record_seconds)):
            data = stream.read(self.chunk_size)
            frames.append(data)

        print("Finished recording.")

        # Stop and close the audio stream
        stream.stop_stream()
        stream.close()
        self.p.terminate()

        # Save the recorded data to a WAV file
        self.save_to_wav(frames)

        # Transcribe the recorded audio
        transcription = self.transcriber.transcribe_audio(self.output_filename)
        return transcription[1]  # Return the transcription text

    def stream_recording(self):
        # Open audio stream
        stream = self.p.open(format=pyaudio.paInt16, channels=1, rate=self.rate,
                             input=True, frames_per_buffer=self.chunk_size, input_device_index=self.input_device_index)

        print("Streaming recording... Press Ctrl+C to stop.")

        transcription_text = ""
        try:
            while True:
                data = stream.read(self.chunk_size)
                transcription = self.transcriber.transcribe_stream([data])
                transcription_text += transcription
                print(f"Streaming Transcription:\n{transcription}")
        except KeyboardInterrupt:
            print("Stopped streaming recording.")

        # Stop and close the audio stream
        stream.stop_stream()
        stream.close()
        self.p.terminate()

        return transcription_text

    def save_to_wav(self, frames):
        with wave.open(self.output_filename, 'wb') as wf:
            wf.setnchannels(1)
            wf.setsampwidth(self.p.get_sample_size(pyaudio.paInt16))
            wf.setframerate(self.rate)
            wf.writeframes(b''.join(frames))
        print(f"Saved to {self.output_filename}")

# Usage
if __name__ == "__main__":
    recorder = AudioRecorder()
    input_device_index = recorder.find_input_device()
    transcription = recorder.record()
    print(f"Transcription:\n{transcription}")
