import pyaudio
import wave
import logging
import os
from dotenv import load_dotenv
from transcribe_audio import Transcriber  # New import
import threading  # Added import
import queue      # Added import
#import webrtcvad  # Added import
import torch  # Added import
import torchaudio  # Added import
import time

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

        # Initialize Voice Activity Detector (VAD)
        # self.vad = webrtcvad.Vad()
        # self.vad.set_mode(1)  # 0: least aggressive, 3: most aggressive

        # Initialize Silero VAD
        self.device = torch.device('cuda' if torch.cuda.is_available() else 'cpu')
        try:
            self.model, utils = torch.hub.load(repo_or_dir='snakers4/silero-vad', model='silero_vad', force_reload=False)
            self.model.to(self.device)
            (self.get_speech_timestamps, _, self.save_audio, _, _) = utils  # Unpack the tuple correctly

            #self.get_speech_timestamps = utils.get_speech_timestamps
            #self.save_audio = utils.save_audio
            logging.info("Silero VAD model loaded successfully.")
        except Exception as e:
            logging.error(f"Failed to load Silero VAD model: {e}")
            raise e

    def find_input_device(self):
        device_count = self.p.get_device_count()
        input_devices = [i for i in range(device_count) if self.p.get_device_info_by_index(i)['maxInputChannels'] > 0]
        
        if len(input_devices) == 1:
            self.input_device_index = input_devices[0]
            device_info = self.p.get_device_info_by_index(self.input_device_index)
            logging.info(f"Only one input device found: {device_info['name']} (index {self.input_device_index})")
            return self.input_device_index
        else:
            for i in input_devices:
                device_info = self.p.get_device_info_by_index(i)
                if self.device_name and self.device_name in device_info['name'].lower():
                    logging.info(f"Found matching device: {device_info['name']} (index {i})")
                    self.input_device_index = i
                    return i
            logging.warning("Suitable input device not found. Using default device.")
            self.input_device_index = None  # PyAudio will use default device
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
        # Initialize queue and transcription threads
        self.transcription_queue = queue.Queue()
        self.transcription_results_queue = queue.Queue()  # Added transcription results queue
        self.transcription_thread = threading.Thread(target=self.process_transcription, daemon=True)
        self.transcription_thread.start()

        # Open audio stream
        stream = self.p.open(format=pyaudio.paInt16, 
                            channels=1, 
                            rate=self.rate,
                            input=True, 
                            frames_per_buffer=self.chunk_size,
                            input_device_index=self.input_device_index,
                            stream_callback=None,
                            start=False)  # Don't start immediately

        print("Recording... Speak now.")
        print("Recording has started.")

        frames = []
        silence_counter = 0
        silence_threshold = 3

        try:
            stream.start_stream()  # Start the stream when ready
            
            while True:
                try:
                    data = stream.read(self.chunk_size, exception_on_overflow=False)
                    frames.append(data)
            
                
                    # Convert byte data to tensor
                    audio_tensor = torch.frombuffer(data, dtype=torch.int16).float()
                    audio_tensor = audio_tensor / 32768.0  # Normalize to [-1, 1]
                    audio_tensor = audio_tensor.unsqueeze(0).to(self.device)
                    
                    # Get speech timestamps using Silero VAD
                    speech_timestamps = self.get_speech_timestamps(audio_tensor, self.model, sampling_rate=self.rate)
                    is_speech = len(speech_timestamps) > 0
                    speech_started = False
                    if is_speech:
                        print("Speech detected. Stopping recording.")
                        speech_started = True
                        # Enqueue the current chunk for transcription
                        self.transcription_queue.put(data)  # Changed from direct transcription
                    else:
                        # Increment silence counter if no speech detected
                        silence_counter += 1
                        if speech_started and silence_counter >= silence_threshold:
                            print("Silence detected. Stopping recording.")
                            break
                        print("no speech, sleeping")
                        time.sleep(0.1)
                        continue  # Skip transcription for silent chunks
                    
                    # Reset silence counter on speech detection
                    silence_counter = 0
                    
                    # Retrieve transcription result
                    try:
                        transcription_chunk = self.transcription_results_queue.get_nowait()
                    except queue.Empty:
                        transcription_chunk = ""

                    # Accumulate transcription text
                    if transcription_chunk:
                        transcription_text += transcription_chunk + "\n"

                    # Update silence counter based on transcription result
                    if transcription_chunk.strip() == "":
                        silence_counter += 1
                        if silence_counter >= silence_threshold:
                            print("Silence detected. Stopping recording.")
                            break
                    else:
                        silence_counter = 0  # Reset counter if speech is detected
                    time.sleep(0.1)
                except IOError as e:
                    if e.errno == pyaudio.paInputOverflowed:
                        print("Warning: Input overflow")
                        stream.read(stream.get_read_available(), exception_on_overflow=False)  # Clear buffer
                        continue
                    else:
                        raise e

        finally:
            stream.stop_stream()
            stream.close()            

        print("Finished recording.")

        # Stop and close the audio stream
        stream.stop_stream()
        stream.close()
        self.p.terminate()

        # Signal transcription thread to terminate
        self.transcription_queue.put(None)
        self.transcription_thread.join()

        # Save the recorded data to a WAV file
        #self.save_to_wav(frames)

        print(f"AudioRecorder record transcribed: {transcription_text.strip()}")
        # Return the full transcription
        return transcription_text.strip()

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
                
                # Convert byte data to tensor
                audio_tensor = torch.frombuffer(data, dtype=torch.int16).float()
                audio_tensor = audio_tensor / 32768.0  # Normalize to [-1, 1]
                audio_tensor = audio_tensor.unsqueeze(0).to(self.device)
                
                # Get speech timestamps using Silero VAD
                speech_timestamps = self.get_speech_timestamps(audio_tensor, self.model, sampling_rate=self.rate)
                is_speech = len(speech_timestamps) > 0
                
                if is_speech:
                    # Enqueue the current chunk for transcription
                    self.transcription_queue.put(data)  # Changed from direct transcription
                else:
                    # Increment silence counter if no speech detected
                    silence_counter += 1
                    if silence_counter >= silence_threshold:
                        print("Silence detected. Stopping streaming recording.")
                        break
                    continue  # Skip transcription for silent chunks
                
                # Reset silence counter on speech detection
                silence_counter = 0
                
                # Retrieve transcription result
                try:
                    transcription_chunk = self.transcription_results_queue.get_nowait()
                except queue.Empty:
                    transcription_chunk = ""
                
                # Accumulate transcription text
                if transcription_chunk:
                    transcription_text += transcription_chunk + "\n"
                
                # Update silence counter based on transcription result
                if transcription_chunk.strip() == "":
                    silence_counter += 1
                    if silence_counter >= silence_threshold:
                        print("Silence detected. Stopping streaming recording.")
                        break
                else:
                    silence_counter = 0  # Reset counter if speech is detected
                
                # Print the latest transcription
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
