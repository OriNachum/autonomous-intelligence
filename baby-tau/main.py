from ollama_service import OllamaService
#import espeak
import argparse
from audio_recorder import AudioRecorder
from response_handler import ResponseHandler  # Updated import

def print_callback(*args):
    print(args)

def get_prompt(args, recorder):
    if args.audio:
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
    system_prompt = """
You are a robot beyond just a model.
You are not just a language model, but also the device that your model runs on.
Reply in jsonl such that the each line convey speech and actions:

{ "speech": "..." }
{ "thinking": "..." }
{ "speech": "..." }
{ "action": "..." }


Make sure to start with speech for faster response time.

Start your answer with {
"""
    return ollama, history_split_with_newline, system_prompt

def main():
    recorder = AudioRecorder()
    parser = argparse.ArgumentParser(description="Run the application.")
    parser.add_argument('--audio', action='store_true', help="Use audio recording for prompt.")
    parser.add_argument('--stream', action='store_true', help="Enable streaming transcription.")
    args = parser.parse_args()

    ollama, history_split_with_newline, system_prompt = initialize_ollama()

    response_handler = ResponseHandler()  # Instantiate ResponseHandler

    if args.audio and args.stream:
        input_device_index = recorder.find_input_device()
        if input_device_index is not None:
            while True:
                transcription = recorder.stream_recording()  # Get transcribed text directly
                if transcription:
                    print(f"Streaming Transcription:\n{transcription}")
                    transcription_text = transcription.split("s]  ")[1]
                    response_handler.process_ollama_response(ollama, transcription_text, history_split_with_newline, system_prompt)  # Updated call
        else:
            print("Audio recording device not found.")
    else:
        prompt = get_prompt(args, recorder)
        if args.audio:
            while True:
                # Pass the recorded audio for transcription
                transcription = recorder.record()  # Get transcribed text directly
                if transcription:
                    print(f"Audio Transcription:\n{transcription}")
                    transcription_text = transcription.split("s]  ")[1]
                    response_handler.process_ollama_response(ollama, transcription_text, history_split_with_newline, system_prompt)  # Updated call
                prompt = get_prompt(args, recorder)
        else:
            print("Write what you say, or /q to exist")
            user = prompt
            in_action = False
            while (user != "/q"):
                if (user != ""):
                    response = ""
                    response_handler.process_ollama_response(ollama, user, history_split_with_newline, system_prompt)  # Updated call
                    history_split_with_newline = response if history_split_with_newline == "" else f"{history_split_with_newline}\n{response}"
                print("Write what you say, or /q to exist")
                user = input()

if __name__ == "__main__":
    main()
