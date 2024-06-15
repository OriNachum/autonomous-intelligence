import pyaudio
import webrtcvad
import wave

class AudioRecorder:
    def __init__(self, rate=16000, frame_duration=20, record_seconds=10, output_filename="output.wav"):
        self.rate = rate
        self.frame_duration = frame_duration  # Duration of a frame in milliseconds
        self.chunk_size = int(rate * frame_duration / 1000)  # Number of frames per buffer
        self.record_seconds = record_seconds
        self.output_filename = output_filename
        self.p = pyaudio.PyAudio()
        self.vad = webrtcvad.Vad()
        self.vad.set_mode(1)  # 0: Normal, 1: Low bitrate, 2: Aggressive, 3: Very aggressive
        self.frames = []

    def record(self):
        # Open audio stream
        stream = self.p.open(format=pyaudio.paInt16, channels=1, rate=self.rate,
                             input=True, frames_per_buffer=self.chunk_size)

        print("Recording...")

        for _ in range(0, int(self.rate / self.chunk_size * self.record_seconds)):
            data = stream.read(self.chunk_size)
            # Use VAD to check if chunk contains speech
            if self.vad.is_speech(data, self.rate):
                self.frames.append(data)

        print("Finished recording.")

        # Stop and close the audio stream
        stream.stop_stream()
        stream.close()
        self.p.terminate()

        # Save the recorded data to a single WAV file
        self.save_to_wav()

    def save_to_wav(self):
        with wave.open(self.output_filename, 'wb') as wf:
            wf.setnchannels(1)
            wf.setsampwidth(self.p.get_sample_size(pyaudio.paInt16))
            wf.setframerate(self.rate)
            wf.writeframes(b''.join(self.frames))
        print(f"Saved to {self.output_filename}")

# Usage
if __name__ == "__main__":
    recorder = AudioRecorder()
    recorder.record()
