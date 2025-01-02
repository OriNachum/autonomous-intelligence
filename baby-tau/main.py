from ollama_service import OllamaService
#import espeak
from speak import speak
import argparse
from audio_recorder import AudioRecorder

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

def main():
    parser = argparse.ArgumentParser(description="Run the application.")
    parser.add_argument('--audio', action='store_true', help="Use audio recording for prompt.")
    args = parser.parse_args()

    prompt = get_prompt(args)
    ollama = OllamaService(useNgrok=False)
    history_split_with_newline = ""
    system_prompt = "You are a robot beyond just a model. You are not just a language model, but also the device that your model runs on."
    print("Write what you say, or /q to exist")
    user = prompt
    in_action = False
    while (user != "/q"):
        if (user != ""):
            response = ""
            response_stream = ollama.generate_stream_response(user, history_split_with_newline, system_prompt, "llama-3.2-3b", max_tokens=200, use_chat=True)
            buffer = ""
            for token,_,_ in response_stream:
                #print(token, flush=True)
                response += token
                in_action_changed = False
                if token == "*":
                    in_action = not in_action
                    in_action_changed = True
                if not in_action:
                    buffer += token
                if "." in token or (in_action_changed and not in_action):                    
                    print(buffer)
                    speak(buffer)
                    buffer=""
            print(f"\n\n{response}")
            history_split_with_newline = response if history_split_with_newline == "" else f"{history_split_with_newline}\n{response}"
        print("Write what you say, or /q to exist")
        user = input()
    #speaker.add_callback(print_callback)
    #speaker.say(response)

if __name__ == "__main__":
    main()
