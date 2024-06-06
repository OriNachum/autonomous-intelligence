import pyaudio
import soundfile as sf
import numpy as np

class SpeechDetector:
    def __init__(self, filename, rate=44100, chunk_size=1024):
        self.filename = filename
        self.rate = rate
        self.chunk_size = chunk_size
        self.p = pyaudio.PyAudio()
        self.stream = None

    def list_devices(self):
        device_count = self.p.get_device_count()
        for i in range(device_count):
            device_info = self.p.get_device_info_by_index(i)
            print(f"Device {i}: {device_info['name']}, Input channels: {device_info['maxInputChannels']}")

    def start_recording(self, duration=10, input_device_index=None):
        try:
            print(f"Opening stream with device index: {input_device_index}")
            self.stream = self.p.open(format=pyaudio.paInt16,
                                      channels=1,
                                      rate=self.rate,
                                      input=True,
                                      input_device_index=input_device_index,
                                      frames_per_buffer=self.chunk_size)
            frames = []
            print("Recording...")

            for _ in range(0, int(self.rate / self.chunk_size * duration)):
                try:
                    data = self.stream.read(self.chunk_size, exception_on_overflow=False)
                    frames.append(data)
                except Exception as e:
                    print(f"Error reading audio stream: {e}")
                    break

            print("Recording complete.")
            audio_data = np.frombuffer(b''.join(frames), dtype=np.int16)

            if len(audio_data) == 0:
                print("Warning: No audio data recorded.")
            else:
                with sf.SoundFile(self.filename, mode='w', samplerate=self.rate, channels=1) as f:
                    f.write(audio_data)
                print(f"Audio data written to {self.filename}")
        except Exception as e:
            print(f"An error occurred during recording: {e}")
        finally:
            if self.stream is not None:
                self.stream.stop_stream()
                self.stream.close()
            self.p.terminate()

    def listen_indefinitely(self, input_device_index=None):
        try:
            print(f"Opening stream with device index: {input_device_index}")
            self.stream = self.p.open(format=pyaudio.paInt16,
                                      channels=1,
                                      rate=self.rate,
                                      input=True,
                                      input_device_index=input_device_index,
                                      frames_per_buffer=self.chunk_size)
            print("Listening... Press Ctrl+C to stop.")
            while True:
                try:
                    data = self.stream.read(self.chunk_size, exception_on_overflow=False)
                    print(f"Received audio data: {len(data)} bytes")
                except Exception as e:
                    print(f"Error reading audio stream: {e}")
                    break
        except KeyboardInterrupt:
            print("Listening stopped by user.")
        except Exception as e:
            print(f"An error occurred during listening: {e}")
        finally:
            if self.stream is not None:
                self.stream.stop_stream()
                self.stream.close()
            self.p.terminate()

# Example usage
detector = SpeechDetector(filename='test.wav')
print("Available audio input devices:")
detector.list_devices()

# Specify the correct input device index
input_device_index = int(input("Enter the device index to use for recording: "))
detector.start_recording(duration=5, input_device_index=input_device_index)
# To listen indefinitely (you can comment out the line above and uncomment the line below)
# detector.listen_indefinitely(input_device_index=input_device_index)
