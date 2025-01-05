import threading
import queue
import time
import logging
from typing import Optional
from speech_transcriber import SpeechTranscriber
from speech_detector import SpeechDetector

class VoiceRecorder:
    def __init__(self, initial_prompt=None, device='cuda', model_size="small"):
        # Configure logging
        logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - VoiceRecorder - %(message)s')
        self.logger = logging.getLogger(__name__)
        
        # Initialize transcriber with the specified settings
        self.transcriber = SpeechTranscriber(initial_prompt=initial_prompt, device=device, model_size=model_size)
        
        self.detector = SpeechDetector(device=device)

        # Queue to store the transcription result
        self.result_queue = queue.Queue()
        
    def _recording_thread(self):
        """Thread function to handle the recording and transcription process."""
        try:
            def handle_transcription(text: str):
                """Callback function to handle transcribed text."""
                if text.strip():  # Only handle non-empty transcriptions
                    self.result_queue.put(text)
                    self.transcriber.stop()  # Stop recording after getting the transcription
            
            # Override the transcriber's process_audio to use our callback
            original_process_audio = self.transcriber.process_audio
            def wrapped_process_audio(in_data, frame_count, time_info, status):
                result = original_process_audio(in_data, frame_count, time_info, status)
                if self.transcriber.speaking == False and self.transcriber.audio_buffer:
                    transcription = self.transcriber.transcribe_audio(self.transcriber.audio_buffer)
                    if transcription:
                        handle_transcription(transcription)
                return result
            
            self.transcriber.process_audio = wrapped_process_audio
            
            # Start the transcriber
            self.transcriber.start()
            
        except Exception as e:
            self.logger.error(f"Error in recording thread: {str(e)}")
            self.result_queue.put(None)  # Signal error to main thread

    def record_and_transcribe(self, timeout=30.0):
        """Record speech and return the transcription."""
        try:
            # Record audio
            audio_data = self.detector.record(timeout=timeout)
            
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
            
            # Transcribe
            segments, info = self.transcriber.transcribe(
                wav_buffer,
                beam_size=5,
                initial_prompt=self.initial_prompt,
                language='en',
                condition_on_previous_text=True
            )
            
            # Collect transcription
            transcription = ""
            for segment in segments:
                transcription += f"{segment.text}\n"
            
            return transcription.strip()
            
        except Exception as e:
            print(f"Error during recording/transcription: {str(e)}")
            return ""
        
    def close(self):
        """Clean up resources."""
        self.detector.close()


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
            # Start the transcriber
            self.transcriber.start()
            
            self.logger.info("Recording started. Speak now...")
            
            # Wait for the result with timeout
            try:
                # Get result from the transcriber's queue
                result = self.transcriber.result_queue.get(timeout=timeout)
                self.logger.info(f"Got result from queue: {result}")
                return result
            except queue.Empty:
                self.logger.warning("Recording timed out - no speech detected")
                return ""
            
        except Exception as e:
            self.logger.error(f"Error during recording: {str(e)}")
            return ""
        
        finally:
            # Ensure cleanup happens
            self.transcriber.stop()

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
