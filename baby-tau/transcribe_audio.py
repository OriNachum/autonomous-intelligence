import sys
import logging
import time
import multiprocessing
from faster_whisper import WhisperModel
import io  # Added import
import wave  # Added import

class Transcriber:
    def __init__(self):
        import logging
        from faster_whisper import WhisperModel
        import multiprocessing
        import time

        # Configure logging for the instance
        logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

        self.process_name = multiprocessing.current_process().name
        logging.info(f"{self.process_name}: Loading Whisper model...")

        # Load the Whisper model once
        self.model = WhisperModel("small", device="cuda", compute_type="int8")
        logging.info(f"{self.process_name}: Model loaded successfully.")

    def transcribe_audio(self, audio_path):
        start_time = time.time()

        # Log before transcription
        logging.info(f"{self.process_name}: Beginning transcription of '{audio_path}'")

        # Transcribe the audio file
        segments, info = self.model.transcribe(audio_path, beam_size=5)

        # Initialize segment counter
        segment_count = 0

        # Collect transcription text
        transcription_text = ""
        logging.info(f"{self.process_name}: Starting to iterate over segments.")
        for i, segment in enumerate(segments):
            segment_length = segment.end - segment.start
            text_length = len(segment.text)
            logging.info(f"{self.process_name}: Segment {i}: Start {segment.start:.2f}s, End {segment.end:.2f}s, Length {segment_length:.2f}s, Text Length: {text_length}")
            transcription_text += f"[{segment.start:.2f}s -> {segment.end:.2f}s] {segment.text}\n"
            segment_count += 1
        logging.info(f"{self.process_name}: Finished iterating over segments.")

        # Calculate transcription time
        transcription_time = time.time() - start_time

        # Log the transcription time and segment count
        logging.info(f"{self.process_name}: Transcribed '{audio_path}' in {transcription_time:.2f} seconds with {segment_count} segments.")
        if segment_count == 0:
            return "", ""

        # Return the transcription text
        return (audio_path, transcription_text)

    def transcribe_stream(self, audio_stream):
        start_time = time.time()

        transcription_text = ""  # Initialize local transcription text

        for chunk in audio_stream:
            # Wrap chunk in WAV format
            if isinstance(chunk, bytes):
                wav_buffer = io.BytesIO()
                with wave.open(wav_buffer, 'wb') as wf:
                    wf.setnchannels(1)
                    wf.setsampwidth(2)  # Assuming 16-bit audio
                    wf.setframerate(16000)  # Ensure this matches the Recorder's rate
                    wf.writeframes(chunk)
                wav_buffer.seek(0)
                chunk = wav_buffer

            # Log before transcription
            logging.info(f"{self.process_name}: Beginning transcription of audio chunk")

            # Transcribe the audio chunk
            segments, info = self.model.transcribe(chunk, beam_size=5)  # Changed 'audio_stream' to 'chunk'

            # Initialize segment counter
            segment_count = 0

            logging.info(f"{self.process_name}: Starting to iterate over segments.")
            for i, segment in enumerate(segments):
                segment_length = segment.end - segment.start
                text_length = len(segment.text)
                logging.info(f"{self.process_name}: Segment {i}: Start {segment.start:.2f}s, End {segment.end:.2f}s, Length {segment_length:.2f}s, Text Length: {text_length}")
                transcription_text += f"[{segment.start:.2f}s -> {segment.end:.2f}s] {segment.text}\n"
                segment_count += 1
            logging.info(f"{self.process_name}: Finished iterating over segments.")

        # Calculate transcription time
        transcription_time = time.time() - start_time

        # Log the transcription time and segment count
        logging.info(f"{self.process_name}: Transcribed audio stream in {transcription_time:.2f} seconds with {segment_count} segments.")

        # Return the transcription text for this chunk
        return transcription_text

def main(audio_files):
    # Configure logging in the main process
    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

    transcriber = Transcriber()

    # Use multiprocessing to transcribe audio files in parallel
    with multiprocessing.Pool(processes=len(audio_files)) as pool:
        results = pool.map(transcriber.transcribe_audio, audio_files)

    # Print transcriptions
    for audio_path, transcription in results:
        print(f"Transcription for '{audio_path}':\n{transcription}\n")

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python transcribe.py <audio_file_path1> [<audio_file_path2> ...]")
        sys.exit(1)

    audio_files = sys.argv[1:]
    main(audio_files)
