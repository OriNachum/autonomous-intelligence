from ollama_service import OllamaService
#import espeak
import subprocess
import threading
import json

def speak(text):
    # Use a new thread to run espeakng in the background
    def espeak_thread():
        try:
            # Run espeakng with the specified language and text
            subprocess.run(["espeak", "-v", "en-us", 
text], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except Exception as e:
            print(f"Error speaking: {e}")

    # Create a new thread to run espeakng
    threading.Thread(target=espeak_thread).start()

def print_callback(*args):
    print(args)



if "__main__" == __name__:
    #espeak.init()
    #speaker = espeak.Espeak()
    ollama = OllamaService(useNgrok=False)
    history_split_with_newline = ""
    system_prompt = "You are a robot beyond just a model. You are not just a language model, but also the device that your model runs on."
    print("Write what you say, or /q to exist")
    user = input()
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
