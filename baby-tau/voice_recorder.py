import threading
import queue
import time
import logging
from typing import Optional
from speech_transcriber import SpeechTranscriber

class VoiceRecorder:
    def __init__(self, device='cuda', model_size="small"):
        # Configure logging
        logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
        self.logger = logging.getLogger(__name__)
        
        # Initialize transcriber with the specified settings
        self.transcriber = SpeechTranscriber(device=device, model_size=model_size)
        
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

    def record(self, timeout: Optional[float] = 30.0) -> str:
        """
        Record audio until speech is detected and transcribed.
        
        Args:
            timeout (float, optional): Maximum time to wait for speech in seconds.
                                     Defaults to 30 seconds.
        
        Returns:
            str: The transcribed text, or empty string if no speech was detected.
        """
        try:
            # Start recording in a separate thread
            thread = threading.Thread(target=self._recording_thread)
            thread.daemon = True
            thread.start()
            
            self.logger.info("Recording started. Speak now...")
            
            # Wait for the result with timeout
            try:
                result = self.result_queue.get(timeout=timeout)
                if result is None:
                    raise RuntimeError("Recording failed")
                return result
            except queue.Empty:
                self.logger.warning("Recording timed out - no speech detected")
                return ""
            
        except Exception as e:
            self.logger.error(f"Error during recording: {str(e)}")
            return ""
        
        finally:
            # Ensure cleanup happens
            if hasattr(self, 'transcriber'):
                self.transcriber.stop()

def main():
    """Example usage of the VoiceRecorder class."""
    recorder = VoiceRecorder()
    
    try:
        print("Press Ctrl+C to stop recording")
        while True:
            print("\nListening for speech...")
            transcription = recorder.record()  # Get transcribed text directly
            
            if transcription:
                print(f"\nTranscription: {transcription}")
            else:
                print("\nNo speech detected, try again...")
            
            # Optional: wait a bit before next recording
            time.sleep(1)
            
    except KeyboardInterrupt:
        print("\nStopping...")
    finally:
        if hasattr(recorder, 'transcriber'):
            recorder.transcriber.stop()

if __name__ == "__main__":
    main()