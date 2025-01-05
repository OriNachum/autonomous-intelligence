import time
import argparse
from ollama_service import OllamaService
#import espeak
from speech_transcriber import SpeechTranscriber
from response_handler import ResponseHandler  # Updated import

def print_callback(*args):
    print(args)

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

def wrap_user_speech(transcription):
    return f"""
{{ "speech": "{transcription}" }}

And remember: reply in jsonl such that the each line convey speech and actions:

{{ "speech": "..." }}
{{ "thinking": "..." }}
{{ "speech": "..." }}
{{ "action": "..." }}

Make sure to start with speech for faster response time.

Start your answer with {{
"""

def main():
    parser = argparse.ArgumentParser(description="Run the application.")
    parser.add_argument('--audio', action='store_true', help="Use audio recording for prompt.")
    parser.add_argument('--stream', action='store_true', help="Enable streaming transcription.")
    args = parser.parse_args()

    ollama, history_split_with_newline, system_prompt = initialize_ollama()

    response_handler = ResponseHandler()  # Instantiate ResponseHandler

    # if args.audio and args.stream:
    #     input_device_index = recorder.record()
    #     if input_device_index is not None:
    #         while True:
    #             transcription = recorder.stream_recording()  # Get transcribed text directly
    #             if transcription:
    #                 print(f"Streaming Transcription:\n{transcription}")
    #                 response_handler.process_ollama_response(ollama, transcription, history_split_with_newline, system_prompt)  # Updated call
    #     else:
    #         print("Audio recording device not found.")
    #else:
    if args.audio:
        def handle_transcription(transcription):
            if transcription:
                user_transcription = wrap_user_speech(transcription)
                print(f"Main: Audio Transcription:\n{user_transcription}")
                response_handler.process_ollama_response(ollama, user_transcription, history_split_with_newline, system_prompt)  # Updated 
            else:
                print("Main: No speech detected")

        transcriber = SpeechTranscriber(handle_transcription, initial_prompt="Speech is english or hebrew", parallel_callback_handling=False)
        print("Starting transcriber. Speak to test (Ctrl+C to exit)...")
        transcriber.start()
    else:
        user = input("Write what you say, or /q to exist")
        while (user != "/q"):
            if (user != ""):
                response = ""
                response_handler.process_ollama_response(ollama, user, history_split_with_newline, system_prompt)  # Updated call
                history_split_with_newline = response if history_split_with_newline == "" else f"{history_split_with_newline}\n{response}"
            user = input("Write what you say, or /q to exist")

if __name__ == "__main__":
    main()
