import time
import argparse
from ollama_service import OllamaService
from speech_transcriber import SpeechTranscriber
from response_handler import ResponseHandler
from voice_recorder import VoiceRecorder

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

    response_handler = ResponseHandler()

    if args.audio:
        recorder = VoiceRecorder()
        while True:
            transcription = recorder.record_and_transcribe()  # Get transcribed text directly
            if transcription:
                user_transcription = wrap_user_speech(transcription)
                print(f"Main: Audio Transcription:\n{user_transcription}")
                response_handler.process_ollama_response(ollama, user_transcription, history_split_with_newline, system_prompt)
            else:
                print("Main: No speech detected")
    else:
        user = input("Write what you say, or /q to exist")
        while (user != "/q"):
            if (user != ""):
                response = ""
                response_handler.process_ollama_response(ollama, user, history_split_with_newline, system_prompt)
                history_split_with_newline = response if history_split_with_newline == "" else f"{history_split_with_newline}\n{response}"
            user = input("Write what you say, or /q to exist")

if __name__ == "__main__":
    main()
