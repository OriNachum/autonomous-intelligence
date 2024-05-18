import pyaudio
import soundfile as sf
import numpy as np
import time
import webrtcvad

class SpeechDetector:
    def __init__(self, lower_threshold=1500, upper_threshold=2500, rate=16000, chunk_duration_ms=30, min_silence_duration=1, filename='temp_audio.wav'):
        self.lower_threshold = lower_threshold
        self.upper_threshold = upper_threshold
        self.rate = rate
        self.chunk_duration_ms = chunk_duration_ms
        self.chunk_size = int(rate * chunk_duration_ms / 1000)
        self.min_silence_duration = min_silence_duration
        self.filename = filename
        self.prev_state = False  # False means volume is not high initially
        self.stop_time = None
        self.start_time = None
        self.detecting = True  # Flag to check if detection is enabled
        self.device_playing = False  # Flag to indicate if device is playing sound
        self.vad = webrtcvad.Vad(2)  # VAD sensitivity (0-3)
        self.speech_events = 0  # Counter for speech events
        self.silence_start_time = None  # Time when silence started
        self.last_silence_duration = None  # Duration of the last silence period

        # Audio setup
        self.p = pyaudio.PyAudio()
        try:
            self.stream = self.p.open(format=pyaudio.paInt16, channels=1, rate=self.rate, input=True, frames_per_buffer=self.chunk_size)
        except IOError as e:
            print(f"Error opening audio stream: {e}")
            raise

    def start_detection(self):
        self.detecting = True
        print("Started detection")

    def stop_detection(self):
        self.detecting = False
        print("Stopped detection")

    def device_start_playback(self):
        self.device_playing = True
        self.stop_detection()  # Pause detection while device is playing
        print("Device started playback")

    def device_stop_playback(self):
        self.device_playing = False
        self.start_detection()  # Resume detection when device stops playing
        print("Device stopped playback")

    def is_speech(self, data):
        # Use VAD to determine if the chunk contains speech
        return self.vad.is_speech(data.tobytes(), self.rate)

    def log_speech_event(self, event_type):
        current_time = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime())
        if event_type == "start":
            silence_duration = 0 if self.last_silence_duration is None else self.last_silence_duration
            print(f"[{current_time}] Speech started (Event #{self.speech_events + 1}), Last silence: {silence_duration:.2f} seconds")
        elif event_type == "stop":
            duration = self.stop_time - self.start_time
            print(f"[{current_time}] Speech stopped (Event #{self.speech_events}) - Duration: {duration:.2f} seconds")

    def run(self):
        print("started")
        # Open WAV file in append mode
        try:
            with sf.SoundFile(self.filename, mode='w', samplerate=self.rate, channels=1) as f:
                while True:
                    # Read audio data
                    data = np.frombuffer(self.stream.read(self.chunk_size, exception_on_overflow=False), dtype=np.int16)

                    # Write audio data to the file
                    f.write(data)

                    if not self.detecting and not self.device_playing:
                        continue

                    # Calculate audio level
                    level = np.max(np.abs(data))

                    # Check if volume is within the valid range and if it is speech
                    if self.lower_threshold < level < self.upper_threshold and self.is_speech(data):
                        if not self.prev_state:  # If volume was not high previously
                            self.start_time = time.time()
                            self.speech_events += 1
                            self.log_speech_event("start")
                            self.prev_state = True  # Update state to indicate volume is now high
                            self.silence_start_time = None  # Reset silence start time

                            if self.device_playing:  # If device is playing sound
                                self.device_stop_playback()  # Stop device playback
                                print("Stopped device playback due to overlapping speech")
                        else:
                            # Reset silence start time if we are in speech
                            self.silence_start_time = None

                    else:
                        if self.prev_state:  # If volume was high previously
                            if self.silence_start_time is None:
                                self.silence_start_time = time.time()
                            elif time.time() - self.silence_start_time >= self.min_silence_duration:
                                self.stop_time = time.time()
                                self.log_speech_event("stop")
                                self.prev_state = False  # Update state to indicate volume is no longer high
                                self.last_silence_duration = time.time() - self.stop_time
                                self.silence_start_time = None  # Reset silence start time
        except Exception as e:
            print(f"Error during audio processing: {e}")
            self.cleanup()
            raise

    def cleanup(self):
        self.stream.stop_stream()
        self.stream.close()
        self.p.terminate()

if __name__ == "__main__":
    detector = SpeechDetector()

    # Simulate event triggers
    try:
        detector.device_start_playback()  # Simulate device starting playback
        time.sleep(2)  # Wait for 2 seconds
        detector.device_stop_playback()  # Simulate device stopping playback
        detector.run()  # Run detection
    except KeyboardInterrupt:
        print("Terminating...")
    finally:
        detector.cleanup()
