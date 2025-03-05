import threading
import queue
import time
import logging
from typing import Optional
import requests
import io
import wave

class VoiceRecorder:
    def __init__(self, initial_prompt=None, device='cuda', model_size="small", stt_url="http://stt:8000/transcribe", vad_url="http://vad:8000/vad"):
        # Configure logging
        logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - VoiceRecorder - %(message)s')
        self.logger = logging.getLogger(__name__)
        
        # Queue to store the transcription result
        self.result_queue = queue.Queue()
        self.stt_url = stt_url
        self.vad_url = vad_url
        
    def _recording_thread(self):
        # ...existing code...

    def record_and_transcribe(self, timeout=30.0):
        """Record speech and return the transcription."""
        try:
            # Record audio
            audio_data = self.record(timeout=timeout)
            
            if audio_data is None:
                print("No speech detected")
                return ""
            
            # Convert audio data to WAV format
            wav_buffer = io.BytesIO()
            with wave.open(wav_buffer, 'wb') as wf:
                wf.setnchannels(1)
                wf.setsampwidth(2)  # 16-bit audio
                wf.setframerate(16000)  # Match the recording rate
                wf.writeframes(audio_data)
            
            # Rewind buffer for reading
            wav_buffer.seek(0)
            
            files = {'audio_file': wav_buffer}
            response = requests.post(self.stt_url, files=files)
            response.raise_for_status()
            
            transcription = response.json().get('text', '')
            return transcription.strip()
            
        except Exception as e:
            print(f"Error during recording/transcription: {str(e)}")
            return ""
        
    def close(self):
        """Clean up resources."""
        pass


    def record(self, timeout: Optional[float] = 2.0) -> str:
        """
        Record audio until speech is detected and transcribed.
        
        Args:
            timeout (float, optional): Maximum time to wait for speech in seconds.
                                     Defaults to 30 seconds.
        
        Returns:
            str: The transcribed text, or empty string if no speech was detected.
        """
        try:
            # Audio settings
            chunk_size = 512  # 512 for 16000 Hz
            rate = 16000
            p = pyaudio.PyAudio()
            input_device_index = self.get_input_device(p)
            
            self.logger.info("Starting recording...")
            stream = p.open(format=pyaudio.paInt16,
                               channels=1,
                               rate=rate,
                               input=True,
                               frames_per_buffer=chunk_size,
                               input_device_index=input_device_index)
            
            start_time = time.time()
            speaking = False
            audio_buffer = []
            
            while time.time() - start_time < timeout:
                in_data = stream.read(chunk_size, exception_on_overflow=False)
                audio_data = np.frombuffer(in_data, dtype=np.int16)
                
                # Convert audio data to WAV format
                wav_buffer = io.BytesIO()
                with wave.open(wav_buffer, 'wb') as wf:
                    wf.setnchannels(1)
                    wf.setsampwidth(2)
                    wf.setframerate(rate)
                    wf.writeframes(in_data)
                wav_buffer.seek(0)
                
                files = {'audio_file': wav_buffer}
                response = requests.post(self.vad_url, files=files)
                response.raise_for_status()
                
                speech_prob = response.json().get('speech_probability', 0.0)
                
                if speech_prob > 0.5:
                    self.logger.info("Speech detected - recording")
                    speaking = True
                    audio_buffer.append(in_data)
                elif speaking:
                    self.logger.info("Speech ended - stopping recording")
                    break
                else:
                    audio_buffer.append(in_data)
            
            stream.stop_stream()
            stream.close()
            p.terminate()
            
            if audio_buffer:
                return b''.join(audio_buffer)
            else:
                return None
            
        except Exception as e:
            self.logger.error(f"Error during recording: {str(e)}")
            return ""

    def get_input_device(self, p):
        """Find the index of the default input device."""
        for i in range(p.get_device_count()):
            device_info = p.get_device_info_by_index(i)
            if device_info['maxInputChannels'] > 0:
                self.logger.info(f"Found input device: {device_info['name']}")
                return i
        return None

def main():
    """Example usage of the VoiceRecorder class with initial prompt."""
    # Example initial prompt to guide transcription
    initial_prompt = "The following is a clear and accurate transcription of speech:"
    
    recorder = VoiceRecorder(initial_prompt=initial_prompt)
    
    try:
        print("Press Ctrl+C to stop recording")
        while True:
            print("\nListening for speech...")
            transcription = recorder.record(timeout=10.0)  # Shorter timeout for testing
            
            if transcription:
                print(f"\nTranscription: {transcription}")
            else:
                print("\nNo speech detected, try again...")
            
            # Optional: wait a bit before next recording
            time.sleep(1)
            
    except KeyboardInterrupt:
        print("\nStopping...")

if __name__ == "__main__":
    main()
