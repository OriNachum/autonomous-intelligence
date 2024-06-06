import pyaudio
import numpy as np
import time
import webrtcvad
import threading
import socket
import os

class SpeechDetector:
    def __init__(self, lower_threshold=1500, upper_threshold=2500, rate=16000, chunk_duration_ms=30, min_silence_duration=1.3):
        self.lower_threshold = lower_threshold
        self.upper_threshold = upper_threshold
        self.rate = rate
        self.chunk_duration_ms = chunk_duration_ms
        self.chunk_size = int(rate * chunk_duration_ms / 1000)
        self.min_silence_duration = min_silence_duration
        self.prev_state = False
        self.stop_time = None
        self.start_time = None
        self.detecting = True
        self.device_playing = False
        self.vad = webrtcvad.Vad(2)
        self.speech_events = 0
        self.silence_start_time = None
        self.last_silence_duration = None

        self.socket_path = "/tmp/tau_hearing_socket"
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
            print(f"Error opening audio stream: {e}")
            raise

    def setup_socket(self):
        if os.path.exists(self.socket_path):
            os.remove(self.socket_path)
        self.sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self.sock.connect(self.socket_path)

    def send_event(self, event_message):
        try:
            self.sock.sendall(event_message.encode('utf-8'))
        except Exception as e:
            print(f"Error sending event: {e}")
            self.cleanup()

    def find_input_device(self):
        device_count = self.p.get_device_count()
        for i in range(device_count):
            device_info = self.p.get_device_info_by_index(i)
            if "default" in device_info['name']:
                print(f"Found suitable input device: {device_info['name']} (index {i})")
                return i
        print("Suitable input device not found")
        return None

    def start_detection(self):
        self.detecting = True
        print("Started detection")

    def stop_detection(self):
        self.detecting = False
        print("Stopped detection")

    def device_start_playback(self):
        self.device_playing = True
        self.stop_detection()
        print("Device started playback")

    def device_stop_playback(self):
        self.device_playing = False
        self.start_detection()
        print("Device stopped playback")

    def is_speech(self, data):
        return self.vad.is_speech(data.tobytes(), self.rate)

    def log_speech_event(self, event_type):
        current_time = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime())
        if event_type == "start":
            silence_duration = 0 if self.last_silence_duration is None else self.last_silence_duration
            message = f"[{current_time}] Speech started (Event #{self.speech_events + 1}), Last silence: {silence_duration:.2f} seconds"
            print(message)
            self.send_event(message)
        elif event_type == "stop":
            duration = self.stop_time - self.start_time
            message = f"[{current_time}] Speech stopped (Event #{self.speech_events}) - Duration: {duration:.2f} seconds"
            print(message)
            self.send_event(message)

    def run(self):
        print("started")
        try:
            while True:
                data = np.frombuffer(self.stream.read(self.chunk_size, exception_on_overflow=False), dtype=np.int16)
                if not self.detecting and not self.device_playing:
                    continue

                level = np.max(np.abs(data))

                if self.lower_threshold < level < self.upper_threshold and self.is_speech(data):
                    if not self.prev_state:
                        self.start_time = time.time()
                        self.speech_events += 1
                        self.log_speech_event("start")
                        self.prev_state = True
                        self.silence_start_time = None
                        if self.device_playing:
                            self.device_stop_playback()
                            print("Stopped device playback due to overlapping speech")
                    else:
                        self.silence_start_time = None
                else:
                    if self.prev_state:
                        if self.silence_start_time is None:
                            self.silence_start_time = time.time()
                        elif time.time() - self.silence_start_time >= self.min_silence_duration:
                            self.stop_time = time.time()
                            self.log_speech_event("stop")
                            self.prev_state = False
                            self.last_silence_duration = self.stop_time - self.silence_start_time
                            self.silence_start_time = None
        except Exception as e:
            print(f"Error during audio processing: {e}")
            self.cleanup()
            raise

    def cleanup(self):
        self.stream.stop_stream()
        self.stream.close()
        self.p.terminate()
        if self.sock:
            self.sock.close()

if __name__ == "__main__":
    detector = SpeechDetector()

    def simulate_device_playback():
        time.sleep(2)
        detector.device_start_playback()
        time.sleep(2)
        detector.device_stop_playback()

    playback_thread = threading.Thread(target=simulate_device_playback)
    playback_thread.start()

    try:
        detector.run()
    except KeyboardInterrupt:
        print("Terminating...")
    finally
        print("Terminating...")
    finally:
        detector.cleanup()
