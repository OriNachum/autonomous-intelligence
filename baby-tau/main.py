from ollama_service import OllamaService
#import espeak
import argparse
from audio_recorder import AudioRecorder
from transcribe_audio import transcribe_stream
from response_handler import process_ollama_response  # New import

def print_callback(*args):
    print(args)

def get_prompt(args):
    if args.audio:
        recorder = AudioRecorder()
        input_device_index = recorder.find_input_device()
        if input_device_index is not None:
            recorder.record()
            return recorder.output_filename  # Return the path to the recorded audio
        else:
            print("Audio recording device not found. Falling back to text input.")
    return input("Enter your prompt: ")

def initialize_ollama():
    ollama = OllamaService(useNgrok=False)
    history_split_with_newline = ""
    system_prompt = "You are a robot beyond just a model. You are not just a language model, but also the device that your model runs on."
    return ollama, history_split_with_newline, system_prompt

def main():
    parser = argparse.ArgumentParser(description="Run the application.")
    parser.add_argument('--audio', action='store_true', help="Use audio recording for prompt.")
    parser.add_argument('--stream', action='store_true', help="Enable streaming transcription.")
    args = parser.parse_args()

    ollama, history_split_with_newline, system_prompt = initialize_ollama()

    if args.audio and args.stream:
        recorder = AudioRecorder()
        input_device_index = recorder.find_input_device()
        if input_device_index is not None:
            audio_stream = recorder.stream_recording()
            transcription = transcribe_stream(audio_stream)
            print(f"Streaming Transcription:\n{transcription}")
            process_ollama_response(ollama, transcription, history_split_with_newline, system_prompt)  # Updated call
        else:
            print("Audio recording device not found.")
    else:
        prompt = get_prompt(args)
        print("Write what you say, or /q to exist")
        user = prompt
        in_action = False
        while (user != "/q"):
            if (user != ""):
                response = ""
                process_ollama_response(ollama, user, history_split_with_newline, system_prompt)  # Updated call
                history_split_with_newline = response if history_split_with_newline == "" else f"{history_split_with_newline}\n{response}"
            print("Write what you say, or /q to exist")
            user = input()

if __name__ == "__main__":
    main()
