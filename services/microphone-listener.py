import pyaudio
import webrtcvad
import wave
import time
import numpy as np
import os
import socket
import sys
import logging

if __name__ == "__main__":
    parent_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    if parent_dir not in sys.path:
        sys.path.append(parent_dir)

from modelproviders.openai_api_client import OpenAIService

# Set up logging
logging.basicConfig(level=logging.DEBUG, format='%(asctime)s %(levelname)s: %(message)s')

class SpeechDetector:
    def __init__(self, lower_threshold=1500, upper_threshold=2500, rate=16000, chunk_duration_ms=30, min_silence_duration=2.0):
        self.lower_threshold = lower_threshold
        self.upper_threshold = upper_threshold
        self.rate = rate
        self.chunk_duration_ms = chunk_duration_ms
        self.chunk_size = int(rate * chunk_duration_ms / 1000)
        self.min_silence_duration = min_silence_duration
        self.vad = webrtcvad.Vad(2)
        self.audio_buffer = []  # List to accumulate audio data during speech
        self.speech_events = 0
        self.silence_start_time = None
        self.speech_detected = False

        self.socket_path = "./sockets/tau_hearing_socket"
        self.setup_socket()

        self.p = pyaudio.PyAudio()
        self.input_device_index = self.find_input_device()
        if self.input_device_index is None:
            raise RuntimeError("Suitable input device not found")

        try:
            self.stream = self.p.open(format=pyaudio.paInt16,
                                      channels=1,
                                      rate=self.rate,
                                      input=True,
                                      frames_per_buffer=self.chunk_size,
                                      input_device_index=self.input_device_index)
        except IOError as e:
            logging.error(f"Error opening audio stream: {e}")
            raise

        self.openai_service = OpenAIService()
        self.output_filename = 'combined_audio.wav'

    def setup_socket(self):
        self.sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self.sock.connect(self.socket_path)

    def send_event(self, event_message):
        try:
            self.sock.sendall(event_message.encode('utf-8'))
        except Exception as e:
            logging.error(f"Error sending event: {e}")
            self.cleanup()

    def find_input_device(self):
        device_count = self.p.get_device_count()
        for i in range(device_count):
            device_info = self.p.get_device_info_by_index(i)
            if "default" == device_info['name']:
                logging.info(f"Found suitable input device: {device_info['name']} (index {i})")
                return i
        logging.warning("Suitable input device not found")
        return None

    def is_speech(self, data):
        try:
            return self.vad.is_speech(data, self.rate)
        except:
            return False

    def log_speech_event(self, event_type, transcript=None):
        current_time = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime())
        if event_type == "start":
            message = f"[{current_time}] Speech started (Event #{self.speech_events + 1})"
            logging.info(message)
            self.send_event(message)
            self.speech_events += 1
        elif event_type == "stop":
            duration = time.time() - self.start_time
            message = f"[{current_time}] Speech stopped (Event #{self.speech_events}) - Duration: {duration:.2f} seconds"
            if transcript:
                message += f" - Transcript: {transcript}"
            logging.info(message)
            self.send_event(message)

    def save_chunk(self, data):
        # Append each audio chunk to the in-memory buffer
        self.audio_buffer.append(data)

    def write_to_file(self):
        # Write the accumulated audio buffer to the WAV file
        with wave.open(self.output_filename, 'wb') as wav_file:
            wav_file.setnchannels(1)
            wav_file.setsampwidth(self.p.get_sample_size(pyaudio.paInt16))  # Ensure correct sample width
            wav_file.setframerate(self.rate)
            wav_file.writeframes(b''.join(self.audio_buffer))
        logging.info(f"Written combined audio to {self.output_filename}")

    def run(self):
        logging.info(f"Starting with chunk size: {self.chunk_size}, rate: {self.rate}")
        try:
            while True:
                data = self.stream.read(self.chunk_size, exception_on_overflow=False)
                if self.is_speech(data):
                    if not self.speech_detected:
                        self.start_time = time.time()
                        self.log_speech_event("start")
                        self.speech_detected = True
                        self.audio_buffer = []

                    self.save_chunk(data)  # Save each chunk to the in-memory buffer
                else:
                    if self.speech_detected:
                        if self.silence_start_time is None:
                            self.silence_start_time = time.time()
                        elif time.time() - self.silence_start_time >= self.min_silence_duration:
                            self.write_to_file()
                            # Perform STT on combined audio data in the buffer
                            combined_audio_data = b''.join(self.audio_buffer)
                            transcript = self.perform_whisper_stt(combined_audio_data)
                            self.log_speech_event("stop", transcript)
                            self.speech_detected = False
                            self.silence_start_time = None
        except webrtcvad.VadError as e:
            logging.error(f"VAD Error: {e}")
            self.cleanup()
            raise
        except Exception as e:
            logging.error(f"Error during audio processing: {e}")
            self.cleanup()
            raise

    def perform_whisper_stt(self, audio_data):
        logging.info("Performing STT with Whisper")
        transcript = self.openai_service.transcribe_audio(audio_data)
        logging.info(f"Transcription result: {transcript}")
        return transcript

    def cleanup(self):
        self.stream.stop_stream()
        self.stream.close()
        self.p.terminate()
        if self.sock:
            self.sock.close()

if __name__ == "__main__":
    detector = SpeechDetector(rate=16000)

    try:
        detector.run()
    except KeyboardInterrupt:
        logging.info("Terminating...")
    finally:
        logging.info("Terminating...")
        detector.cleanup()
