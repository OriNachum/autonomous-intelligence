import sounddevice as sd
import numpy as np
import requests
import openai
import torch
# import torchaudio # Not directly needed now, but silero_vad might use it internally
import scipy.io.wavfile as wavfile
import io
import time
import os
import tempfile
from playsound import playsound # Simple playback library
import soundfile as sf # For fallback playback loading
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()
TTS_VOICE = os.getenv("TTS_VOICE", "af_alloy")  # Default to 'af_alloy' if not set
VAD_EVERY_N_CHUNKS = int(os.getenv("VAD_EVERY_N_CHUNKS", 3))  # Default to 1 if not set

# --- Import Silero VAD ---
try:
    from silero_vad import load_silero_vad
except ImportError:
    print("Error: 'silero_vad' package not found.")
    print("Please install it: pip install -U silero-vad")
    exit(1)
except Exception as e:
    print(f"Error importing Silero VAD: {e}")
    print("Ensure PyTorch is installed correctly.")
    exit(1)


# --- Configuration ---
# API Endpoints
STT_URL = "http://localhost:8001/v1/audio/transcriptions"
LLM_URL = "http://localhost:8000/v1" # Base URL for OpenAI compatible API
LLM_MODEL = os.getenv("LLM_MODEL") # Or your specific local model
TTS_URL = "http://localhost:8880/v1/audio/speech" # Or your TTS endpoint

# Audio Settings
SAMPLE_RATE = 16000 # Sample rate expected by Silero VAD
CHANNELS = 1
BLOCK_SIZE = 512   # Process smaller chunks for faster VAD response (adjust as needed)
DTYPE = 'int16'     # Data type for recording

# VAD Settings
MIN_SILENCE_DURATION_MS = 1000 # How long silence indicates end of speech
VAD_THRESHOLD = 0.5  # VAD confidence threshold (adjust as needed)
SPEECH_PAD_MS = 300    # Add slight padding around detected speech

# Calculate VAD related timing in terms of chunks
ms_per_chunk = (BLOCK_SIZE / SAMPLE_RATE) * 1000
num_padding_chunks = int(SPEECH_PAD_MS / ms_per_chunk)
num_silent_chunks_needed = int(MIN_SILENCE_DURATION_MS / ms_per_chunk)

PRESPEECH_BUFFER_SECONDS = 2  # Amount of audio to keep before speech detection
max_prespeech_chunks = int(PRESPEECH_BUFFER_SECONDS * SAMPLE_RATE / BLOCK_SIZE)

# --- Initialize VAD ---
print("Loading Silero VAD model...")
try:
    # Use the direct function from the silero_vad package
    vad_model = load_silero_vad() # Set force_reload=True if download issues
    print("Silero VAD model loaded successfully.")
except Exception as e:
    print(f"Error initializing Silero VAD: {e}")
    print("Please ensure you have torch installed correctly.")
    print("Check network connection if model download fails.")
    exit(1)


# --- Initialize OpenAI Client ---
# Point the OpenAI client to your local LLM endpoint
try:
    client = openai.OpenAI(base_url=LLM_URL, api_key="not-needed-for-local")
except Exception as e:
    print(f"Error initializing OpenAI client: {e}")
    exit(1)

# --- Main Loop ---
def main_loop():
    print("\nStarting voice assistant loop (using sounddevice and silero_vad). Press Ctrl+C to exit.")
    # Optional: Specify device index or name if default isn't correct
    # sd.query_devices() # Uncomment to see available devices
    # input_device = None # Use default device

    # State variables for VAD processing
    audio_buffer = []
    triggered = False
    silent_chunks = 0
    leading_chunks_buffer = []

    try:
        with sd.RawInputStream(samplerate=SAMPLE_RATE,
                               blocksize=BLOCK_SIZE,
                               channels=CHANNELS,
                               dtype=DTYPE,
                               # device=input_device # Specify device if needed
                               ) as stream:

            print(f"\nSounddevice stream opened: SR={SAMPLE_RATE}, Block={BLOCK_SIZE}, Format={DTYPE}")
            print(f"VAD Settings: Threshold={VAD_THRESHOLD}, Min Silence={MIN_SILENCE_DURATION_MS}ms, Padding={SPEECH_PAD_MS}ms")
            print("Listening...")
            temp_vad_every_n_chunks = VAD_EVERY_N_CHUNKS # For debugging
            while True: # Outer loop: Continues after processing an utterance
                # Reset state for the next utterance
                audio_buffer = []
                triggered = False
                silent_chunks = 0
                prespeech_buffer = []  # Circular buffer for pre-speech audio
                chunk_counter = 0  # Initialize chunk counter

                while True: # Inner loop to capture one full utterance
                    # Read audio chunk from sounddevice stream
                    audio_chunk_raw, overflowed = stream.read(BLOCK_SIZE)
                    if overflowed:
                        print(f"Warning: Input overflowed! Processing might be too slow. Consider increasing VAD_EVERY_N_CHUNKS: {VAD_EVERY_N_CHUNKS}.")
                        temp_vad_every_n_chunks += 1 # Increase chunk processing interval to reduce load
                    
                    # Convert raw bytes to numpy array for all chunks (needed whether we do VAD or not)
                    audio_chunk_np = np.frombuffer(audio_chunk_raw, dtype=np.int16)
                    if audio_chunk_np.size == 0:
                        # print("Warning: Read empty chunk.") # Can happen, usually ignorable
                        continue
                    
                    # Always maintain pre-speech buffer
                    prespeech_buffer.append(audio_chunk_np)
                    if len(prespeech_buffer) > max_prespeech_chunks:
                        prespeech_buffer.pop(0)
                    
                    # If speech has already been triggered, always add the chunk to the buffer
                    if triggered:
                        audio_buffer.append(audio_chunk_np)
                    
                    # Small delay to avoid overwhelming the stream
                    time.sleep(0.015)
                    
                    # Increment chunk counter and process VAD only every N chunks
                    chunk_counter = (chunk_counter + 1) % temp_vad_every_n_chunks
                    if chunk_counter != 0:
                        # For non-VAD chunks, update silence tracking if needed
                        if triggered:
                            # If we're in triggered state but not checking VAD, 
                            # we still need to track potential silence
                            # This is a simplified approach - more sophisticated would be to do
                            # quick energy check instead of skipping silence detection entirely
                            continue
                        else:
                            # Not triggered and not checking VAD, just continue
                            continue

                    # Append to leading buffer (used for padding before speech starts)
                    # Only store in leading buffer if not triggered yet
                    if not triggered:
                        leading_chunks_buffer.append(audio_chunk_np)
                        if len(leading_chunks_buffer) > num_padding_chunks:
                            leading_chunks_buffer.pop(0) # Keep buffer size limited

                    # Normalize to [-1.0, 1.0] - VAD expects float tensor
                    audio_chunk_tensor = torch.from_numpy(audio_chunk_np).float() / 32768.0
                    
                    # --- Simple VAD Logic using silero_vad model ---
                    try:
                        # The model requires the sample rate on each call with this direct method
                        speech_prob = vad_model(audio_chunk_tensor, SAMPLE_RATE).item()
                    except Exception as e:
                        print(f"Error during VAD processing chunk: {e}")
                        # Decide how to handle - skip chunk? Reset? For now, continue.
                        continue

                    if speech_prob >= VAD_THRESHOLD:
                        silent_chunks = 0 # Reset silence counter
                        if not triggered:
                            print("Speech started...")
                            triggered = True
                            # Add pre-speech buffer to the start of audio_buffer
                            audio_buffer.extend(prespeech_buffer)
                            prespeech_buffer.clear()
                            # Add leading padding from buffer
                            audio_buffer.extend(leading_chunks_buffer)
                            leading_chunks_buffer.clear() # Clear once used
                            # Note: current chunk already added to buffer above if triggered
                    elif triggered: # Speech was active, now potentially silence
                        # Note: we already added this chunk to audio_buffer earlier
                        silent_chunks += 1
                        # print(f"Silent chunk {silent_chunks}/{num_silent_chunks_needed}") # Debugging

                        if silent_chunks >= num_silent_chunks_needed:
                            print(f"Speech ended detected after ~{silent_chunks * ms_per_chunk:.0f}ms silence.")
                            # Add padding implicitly by having recorded these silent chunks
                            # Trim excess silence/padding if necessary (optional refinement)
                            # For now, break after enough silence
                            break # Exit inner loop, process the recording
                    else:
                        # Still silent, and not triggered yet. Do nothing except maintain leading buffer.
                        pass
                        # print(".", end="", flush=True) # Optional: Indicate listening

                # --- End of Inner Loop (Utterance detected) ---

                if not audio_buffer:
                    # This should ideally not happen if logic is correct, but as a safeguard
                    print("No audio captured despite VAD trigger/end logic.")
                    continue # Go back to listening

                # --- Process Recorded Audio ---
                print("Processing captured audio...")
                full_audio = np.concatenate(audio_buffer)
                # audio_buffer = [] # Already cleared at the start of the outer loop

                print(f"Captured audio duration: {len(full_audio)/SAMPLE_RATE:.2f} seconds")

                # Save to a temporary WAV file
                tmp_wav_path = None # Define outside try block for finally
                tts_audio_path = None # Define outside try block for finally
                try:
                    # Use a context manager for safer temp file handling
                    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp_wav:
                        wavfile.write(tmp_wav.name, SAMPLE_RATE, full_audio)
                        tmp_wav_path = tmp_wav.name
                    # print(f"Audio saved to temporary file: {tmp_wav_path}") # Debugging

                    # --- STT / LLM / TTS Steps (Identical logic to original) ---
                    transcription = None
                    llm_response_text = None

                    # 1. Send to STT
                    print("Sending audio to STT...")
                    try:
                        with open(tmp_wav_path, 'rb') as f:
                            files = {'file': (os.path.basename(tmp_wav_path), f, 'audio/wav')}
                            # Adjust payload as needed for your STT service
                            stt_payload = { "model": "Systran/faster-whisper-tiny", "language": "en" } # Example for OpenAI compatible STT
                            print(f"STT Payload: {stt_payload}") # Debugging
                            response = requests.post(STT_URL, files=files, data=stt_payload)
                            response.raise_for_status() # Raise HTTPError for bad responses (4xx or 5xx)
                            stt_result = response.json()
                            print(stt_result) # Debugging
                            # Try common keys for transcription text
                            transcription = stt_result.get('text') or \
                                            stt_result.get('transcript') or \
                                            (stt_result.get('results', [{}])[0].get('transcript') if stt_result.get('results') else None)

                            if transcription:
                                print(f"STT Result: {transcription}")
                            else:
                                print(f"Could not find transcription text in STT response: {stt_result}")

                    except requests.exceptions.RequestException as e:
                        response_text = ""
                        if hasattr(e, 'response') and e.response is not None:
                            try: response_text = f" Response: {e.response.text}"
                            except: pass # Avoid errors reading response
                        print(f"STT request failed: {e}{response_text}")
                    except Exception as e:
                        print(f"Error processing STT response: {e}")


                    # 2. Send Transcription to LLM
                    if transcription:
                        print("Sending transcription to LLM...")
                        try:
                            # Use ChatCompletion for conversational models
                            completion = client.chat.completions.create(
                                model=LLM_MODEL,
                                messages=[
                                    {"role": "system", "content": "You are a helpful voice assistant."},
                                    {"role": "user", "content": transcription}
                                ],
                                temperature=0.7 # Adjust creativity/randomness
                                # max_tokens=150 # Optionally limit response length
                            )
                            llm_response_text = completion.choices[0].message.content
                            print(f"LLM Response: {llm_response_text}")
                        except openai.APIConnectionError as e: print(f"LLM connection error: {e}")
                        except openai.RateLimitError as e: print(f"LLM rate limit exceeded: {e}")
                        except openai.APIStatusError as e: print(f"LLM API error ({LLM_MODEL}) (status {e.status_code}): {e.response}")
                        except Exception as e: print(f"LLM request failed: {e}")

                    # 3. Send LLM Response to TTS
                    if llm_response_text:
                        print("Sending LLM response to TTS...")
                        # Adjust payload for your TTS service (e.g., Piper, Coqui, OpenAI TTS)
                        tts_payload = {
                            "input": llm_response_text,
                            "voice": TTS_VOICE,  # Use the configurable voice
                            "response_format": "wav",  # Request WAV for wider compatibility
                            # Add other TTS specific parameters here
                         }
                        tts_format = tts_payload.get('response_format', 'wav') # Default to wav

                        try:
                            response = requests.post(TTS_URL, json=tts_payload, stream=True) # Use stream=True if large response
                            response.raise_for_status()

                            with tempfile.NamedTemporaryFile(suffix=f".{tts_format}", delete=False) as tmp_tts:
                                for chunk in response.iter_content(chunk_size=8192):
                                    tmp_tts.write(chunk)
                                tts_audio_path = tmp_tts.name
                            print(f"TTS audio saved to: {tts_audio_path}")

                        except requests.exceptions.RequestException as e:
                            response_text = ""
                            if hasattr(e, 'response') and e.response is not None:
                                try: response_text = f" Response: {e.response.text}"
                                except: pass
                            print(f"TTS request failed: {e}{response_text}")
                        except Exception as e:
                            print(f"Error processing TTS response or saving audio: {e}")

                    # 4. Play TTS Audio
                    if tts_audio_path:
                        print("Playing TTS response...")
                        try:
                            # Try playsound first (simple, might need GStreamer/other backend)
                            playsound(tts_audio_path)
                            print("Playback finished (playsound).")
                        except Exception as e_ps:
                            print(f"Error playing audio with playsound: {e_ps}")
                            print("Trying playback with soundfile/sounddevice as fallback...")
                            try:
                                # Use soundfile to read various formats (like WAV)
                                data, fs = sf.read(tts_audio_path, dtype='float32')
                                print(f"Attempting sounddevice playback: SR={fs}, Channels={data.ndim}")
                                sd.play(data, fs, blocking=True) # Use blocking=True to wait
                                # sd.wait() # Not needed if blocking=True
                                print("Playback finished (sounddevice).")
                            except Exception as fallback_e:
                                print(f"Fallback playback with soundfile/sounddevice also failed: {fallback_e}")
                                print("Ensure you have 'libsndfile' installed if using soundfile (sudo apt-get install libsndfile1)")
                    elif llm_response_text:
                        print("TTS failed, cannot play response.")
                    else:
                         print("Nothing to say (No LLM response).")


                finally:
                     # Clean up temporary files
                    if tmp_wav_path and os.path.exists(tmp_wav_path):
                        try: os.remove(tmp_wav_path)
                        except OSError as e: print(f"Error removing temp WAV file {tmp_wav_path}: {e}")
                    if tts_audio_path and os.path.exists(tts_audio_path):
                         try: os.remove(tts_audio_path)
                         except OSError as e: print(f"Error removing temp TTS file {tts_audio_path}: {e}")

                # Ready for next utterance
                print("\nListening...")


    except KeyboardInterrupt:
        print("\nExiting loop.")
    except sd.PortAudioError as e:
        print(f"\nSounddevice PortAudioError: {e}")
        print("Please check your audio device configuration and permissions.")
        # Add more specific troubleshooting tips if needed
    except Exception as e:
        # Catch other potential errors
        print(f"\nAn unexpected error occurred in the main loop: {e}")
        import traceback
        traceback.print_exc() # Print detailed traceback for debugging
    finally:
        print("Cleanup complete. Exiting.")


if __name__ == "__main__":
    main_loop()
