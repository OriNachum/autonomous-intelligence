import pyaudio
import wave
import logging
import os
from dotenv import load_dotenv
from transcribe_audio import Transcriber  # New import
import threading  # Added import
import queue      # Added import

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

        # Initialize queue and transcription threads
        self.transcription_queue = queue.Queue()
        self.transcription_results_queue = queue.Queue()  # Added transcription results queue
        self.transcription_text = ""
        self.transcription_thread = threading.Thread(target=self.process_transcription, daemon=True)
        self.transcription_thread.start()

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

    def process_transcription(self):
        while True:
            data = self.transcription_queue.get()
            if data is None:
                break  # Exit signal
            try:
                # Transcribe the audio chunk
                transcription_chunk = self.transcriber.transcribe_stream([data])
                self.transcription_results_queue.put(transcription_chunk.strip())  # Enqueue transcription result
                print(f"Transcription Chunk: {transcription_chunk.strip()}")
            except Exception as e:
                logging.error(f"Error during transcription: {e}")
                self.transcription_results_queue.put("")  # Enqueue empty string on error
        logging.info("Transcription thread terminated.")

    def record(self):
        # Open audio stream
        stream = self.p.open(format=pyaudio.paInt16, channels=1, rate=self.rate,
                             input=True, frames_per_buffer=self.chunk_size, input_device_index=self.input_device_index)

        print("Recording... Speak now.")
        print("Recording has started.")  # Added indication

        frames = []
        silence_counter = 0
        silence_threshold = 3  # Number of consecutive silent chunks to stop

        while True:
            data = stream.read(self.chunk_size)
            frames.append(data)

            # Enqueue the current chunk for transcription
            self.transcription_queue.put(data)  # Changed from direct transcription

            # Retrieve transcription result
            try:
                transcription_chunk = self.transcription_results_queue.get_nowait()
            except queue.Empty:
                transcription_chunk = ""

            # Update silence counter based on transcription result
            if transcription_chunk == "" and self.transcription_text.strip() != "":
                silence_counter += 1
                if silence_counter >= silence_threshold:
                    print("Silence detected. Stopping recording.")
                    break
            else:
                silence_counter = 0  # Reset counter if speech is detected

        print("Finished recording.")

        # Stop and close the audio stream
        stream.stop_stream()
        stream.close()
        self.p.terminate()

        # Signal transcription thread to terminate
        self.transcription_queue.put(None)
        self.transcription_thread.join()

        # Save the recorded data to a WAV file
        self.save_to_wav(frames)

        # Return the full transcription
        return self.transcription_text.strip()

    def stream_recording(self):
        # Open audio stream
        stream = self.p.open(format=pyaudio.paInt16, channels=1, rate=self.rate,
                             input=True, frames_per_buffer=self.chunk_size, input_device_index=self.input_device_index)

        print("Streaming recording... Press Ctrl+C to stop.")

        transcription_text = ""
        silence_counter = 0
        silence_threshold = 2  # Number of consecutive silent chunks to stop

        try:
            while True:
                data = stream.read(self.chunk_size)
                # Enqueue the current chunk for transcription
                self.transcription_queue.put(data)  # Changed from direct transcription

                # Retrieve transcription result
                try:
                    transcription_chunk = self.transcription_results_queue.get_nowait()
                except queue.Empty:
                    transcription_chunk = ""

                # Update silence counter based on transcription result
                if transcription_chunk == "":
                    silence_counter += 1
                    if silence_counter >= silence_threshold:
                        print("Silence detected. Stopping streaming recording.")
                        break
                else:
                    silence_counter = 0  # Reset counter if speech is detected

                # Accumulate transcription text
                transcription_text += transcription_chunk + "\n"
                print(f"Streaming Transcription:\n{transcription_text.strip()}")
        except KeyboardInterrupt:
            print("Stopped streaming recording.")

        # Stop and close the audio stream
        stream.stop_stream()
        stream.close()
        self.p.terminate()

        # Signal transcription thread to terminate
        self.transcription_queue.put(None)
        self.transcription_thread.join()

        return transcription_text.strip()

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
