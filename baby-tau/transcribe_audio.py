import sys
import logging
import time
import multiprocessing
from faster_whisper import WhisperModel

def transcribe_audio(audio_path):
    import time
    import logging
    from faster_whisper import WhisperModel

    # Configure logging for each process
    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

    process_name = multiprocessing.current_process().name
    logging.info(f"{process_name}: Loading Whisper model...")

    # Load the Whisper model
    model = WhisperModel("small", device="cuda", compute_type="int8")
    logging.info(f"{process_name}: Model loaded successfully.")

    start_time = time.time()

    # Log before transcription
    logging.info(f"{process_name}: Beginning transcription of '{audio_path}'")

    # Transcribe the audio file
    segments, info = model.transcribe(audio_path, beam_size=5)

    # Initialize segment counter
    segment_count = 0

    # Collect transcription text
    transcription_text = ""

    logging.info(f"{process_name}: Starting to iterate over segments.")
    for i, segment in enumerate(segments):
        segment_length = segment.end - segment.start
        text_length = len(segment.text)
        logging.info(f"{process_name}: Segment {i}: Start {segment.start:.2f}s, End {segment.end:.2f}s, Length {segment_length:.2f}s, Text Length: {text_length}")
        transcription_text += f"[{segment.start:.2f}s -> {segment.end:.2f}s] {segment.text}\n"
        segment_count += 1
    logging.info(f"{process_name}: Finished iterating over segments.")

    # Calculate transcription time
    transcription_time = time.time() - start_time

    # Log the transcription time and segment count
    logging.info(f"{process_name}: Transcribed '{audio_path}' in {transcription_time:.2f} seconds with {segment_count} segments.")

    # Return the transcription text
    return (audio_path, transcription_text)

# Add the streaming transcription function
def transcribe_stream(audio_stream):
    import sys
    import logging
    import time
    import multiprocessing
    from faster_whisper import WhisperModel

    # Configure logging for each process
    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

    process_name = multiprocessing.current_process().name
    logging.info(f"{process_name}: Loading Whisper model...")

    # Load the Whisper model
    model = WhisperModel("small", device="cuda", compute_type="int8")
    logging.info(f"{process_name}: Model loaded successfully.")

    start_time = time.time()

    for chunk in audio_stream:
    # Log before transcription
    logging.info(f"{process_name}: Beginning transcription of audio stream")

    # Transcribe the audio stream
    segments, info = model.transcribe(audio_stream, beam_size=5)

    # Initialize segment counter
    segment_count = 0

    # Collect transcription text
    transcription_text = ""

    logging.info(f"{process_name}: Starting to iterate over segments.")
    for i, segment in enumerate(segments):
        segment_length = segment.end - segment.start
        text_length = len(segment.text)
        logging.info(f"{process_name}: Segment {i}: Start {segment.start:.2f}s, End {segment.end:.2f}s, Length {segment_length:.2f}s, Text Length: {text_length}")
        transcription_text += f"[{segment.start:.2f}s -> {segment.end:.2f}s] {segment.text}\n"
        segment_count += 1
    logging.info(f"{process_name}: Finished iterating over segments.")

    # Calculate transcription time
    transcription_time = time.time() - start_time

    # Log the transcription time and segment count
    logging.info(f"{process_name}: Transcribed audio stream in {transcription_time:.2f} seconds with {segment_count} segments.")

    # Return the transcription text
    return transcription_text

def main(audio_files):
    # Configure logging in the main process
    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

    # Use multiprocessing to transcribe audio files in parallel
    with multiprocessing.Pool(processes=len(audio_files)) as pool:
        results = pool.map(transcribe_audio, audio_files)

    # Print transcriptions
    for audio_path, transcription in results:
        print(f"Transcription for '{audio_path}':\n{transcription}\n")

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python transcribe.py <audio_file_path1> [<audio_file_path2> ...]")
        sys.exit(1)

    audio_files = sys.argv[1:]
    main(audio_files)

        # Here, you would process each chunk with WhisperModel
        # Assuming WhisperModel has a method for incremental transcription
        segments, info = model.transcribe_chunk(chunk, beam_size=5)
        for segment in segments:
            transcription_text += f"[{segment.start:.2f}s -> {segment.end:.2f}s] {segment.text}\n"
            logging.info(f"{process_name}: Transcribed chunk: {segment.text}")

    logging.info(f"{process_name}: Finished streaming transcription.")
    return transcription_text

def main(audio_files):
    # Configure logging in the main process
    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

    # Use multiprocessing to transcribe audio files in parallel
    with multiprocessing.Pool(processes=len(audio_files)) as pool:
        results = pool.map(transcribe_audio, audio_files)

    # Print transcriptions
    for audio_path, transcription in results:
        print(f"Transcription for '{audio_path}':\n{transcription}\n")

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python transcribe.py <audio_file_path1> [<audio_file_path2> ...]")
        sys.exit(1)

    audio_files = sys.argv[1:]
    main(audio_files)
