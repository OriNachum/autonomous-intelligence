
from speak import speak

def process_ollama_response(ollama, prompt, history, system_prompt):
    response_stream = ollama.generate_stream_response(
        prompt,
        history,
        system_prompt,
        "llama-3.2-3b",
        max_tokens=200,
        use_chat=True
    )
    buffer = ""
    in_action = False
    for token, _, _ in response_stream:
        #buffer += token
        in_action_changed = False
        if token == "*":
            in_action = not in_action
            in_action_changed = True
        if not in_action:
            buffer += token
        if "." in token or (in_action_changed and not in_action):
            print(buffer)
            speak(buffer)
            buffer = ""
    print(f"\n\nStreaming Response from Ollama:\n{buffer}")