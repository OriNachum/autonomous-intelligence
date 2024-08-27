import pyaudio
import webrtcvad
import wave
import time
import numpy as np
import os
import socket
import sys
import logging
from dotenv import load_dotenv

# Set up logging
logging.basicConfig(level=logging.DEBUG, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)
logger.info("Speech Detector application starting...")

# Load environment variables
load_dotenv()
logger.debug("Environment variables loaded")

if __name__ == "__main__":
    parent_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    if parent_dir not in sys.path:
        sys.path.append(parent_dir)
        logger.debug(f"Added {parent_dir} to sys.path")

from modelproviders.openai_api_client import OpenAIService

class SpeechDetector:
    def __init__(self, lower_threshold=1500, upper_threshold=2500, rate=16000, chunk_duration_ms=30, min_silence_duration=2.0):
        logger.info("Initializing SpeechDetector")
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
        self.device_name = os.getenv('AUDIO_DEVICE_NAME', 'default').lower()
        logger.debug(f"Using audio device: {self.device_name}")

        self.input_device_index = self.find_input_device()
        if self.input_device_index is None:
            logger.error("Suitable input device not found")
            raise RuntimeError("Suitable input device not found")

        try:
            self.stream = self.p.open(format=pyaudio.paInt16,
                                      channels=1,
                                      rate=self.rate,
                                      input=True,
                                      frames_per_buffer=self.chunk_size,
                                      input_device_index=self.input_device_index)
            logger.info("Audio stream opened successfully")
        except IOError as e:
            logger.error(f"Error opening audio stream: {e}")
            raise

        self.openai_service = OpenAIService()
        logger.debug("OpenAIService initialized")
        self.output_filename = 'combined_audio.wav'
        logger.info("SpeechDetector initialization complete")

    def setup_socket(self):
        logger.debug(f"Setting up Unix socket at {self.socket_path}")
        self.sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        try:
            self.sock.connect(self.socket_path)
            logger.info("Successfully connected to Unix socket")
        except Exception as e:
            logger.error(f"Failed to connect to Unix socket: {e}")
            raise

    def send_event(self, event_message):
        try:
            self.sock.sendall(event_message.encode('utf-8'))
            logger.debug(f"Sent event: {event_message}")
        except Exception as e:
            logger.error(f"Error sending event: {e}")
            self.cleanup()

    def find_input_device(self):
        logger.info("Searching for input device")
        device_count = self.p.get_device_count()
        for i in range(device_count):
            device_info = self.p.get_device_info_by_index(i)
            if self.device_name in device_info['name'].lower():
                logger.info(f"Found matching device: {device_info['name']} (index {i})")
                return i
        logger.warning("Suitable input device not found")
        return None

    def is_speech(self, data):
        try:
            return self.vad.is_speech(data, self.rate)
        except Exception as e:
            logger.error(f"Error in VAD processing: {e}")
            return False

    def log_speech_event(self, event_type, transcript=None):
        current_time = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime())
        if event_type == "start":
            message = f"[{current_time}] Speech started (Event #{self.speech_events + 1})"
            logger.info(message)
            self.send_event(message)
            self.speech_events += 1
        elif event_type == "stop":
            duration = time.time() - self.start_time
            message = f"[{current_time}] Speech stopped (Event #{self.speech_events}) - Duration: {duration:.2f} seconds"
            if transcript:
                message += f" - Transcript: {transcript}"
            logger.info(message)
            self.send_event(message)

    def save_chunk(self, data):
        self.audio_buffer.append(data)
        logger.debug(f"Saved audio chunk. Buffer size: {len(self.audio_buffer)}")

    def write_to_file(self):
        logger.info(f"Writing combined audio to {self.output_filename}")
        with wave.open(self.output_filename, 'wb') as wav_file:
            wav_file.setnchannels(1)
            wav_file.setsampwidth(self.p.get_sample_size(pyaudio.paInt16))
            wav_file.setframerate(self.rate)
            wav_file.writeframes(b''.join(self.audio_buffer))
        logger.info(f"Written combined audio to {self.output_filename}")

    def run(self):
        logger.info(f"Starting speech detection with chunk size: {self.chunk_size}, rate: {self.rate}")
        try:
            while True:
                data = self.stream.read(self.chunk_size, exception_on_overflow=False)
                if self.is_speech(data):
                    if not self.speech_detected:
                        self.start_time = time.time()
                        self.log_speech_event("start")
                        self.speech_detected = True
                        self.audio_buffer = []
                        logger.debug("Speech detected, starting new buffer")

                    self.save_chunk(data)
                else:
                    if self.speech_detected:
                        if self.silence_start_time is None:
                            self.silence_start_time = time.time()
                            logger.debug("Silence detected, starting silence timer")
                        elif time.time() - self.silence_start_time >= self.min_silence_duration:
                            logger.info("Silence duration exceeded, processing speech")
                            self.write_to_file()
                            combined_audio_data = b''.join(self.audio_buffer)
                            transcript = self.perform_whisper_stt(combined_audio_data)
                            self.log_speech_event("stop", transcript)
                            self.speech_detected = False
                            self.silence_start_time = None
        except webrtcvad.VadError as e:
            logger.error(f"VAD Error: {e}")
            self.cleanup()
            raise
        except Exception as e:
            logger.error(f"Error during audio processing: {e}", exc_info=True)
            self.cleanup()
            raise

    def perform_whisper_stt(self, audio_data):
        logger.info("Performing STT with Whisper")
        try:
            transcript = self.openai_service.transcribe_audio(audio_data)
            logger.info(f"Transcription result: {transcript}")
            return transcript
        except Exception as e:
            logger.error(f"Error during transcription: {e}", exc_info=True)
            return "Transcription failed"

    def cleanup(self):
        logger.info("Cleaning up resources")
        if hasattr(self, 'stream'):
            self.stream.stop_stream()
            self.stream.close()
        if hasattr(self, 'p'):
            self.p.terminate()
        if hasattr(self, 'sock'):
            self.sock.close()
        logger.info("Cleanup complete")

if __name__ == "__main__":
    detector = SpeechDetector(rate=16000)

    try:
        detector.run()
    except KeyboardInterrupt:
        logger.info("Keyboard interrupt received, terminating...")
    except Exception as e:
        logger.error(f"Unexpected error: {e}", exc_info=True)
    finally:
        logger.info("Terminating speech detector...")
        detector.cleanup()
