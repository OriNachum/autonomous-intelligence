
from speak import speak_piper

def process_ollama_response(ollama, prompt, history, system_prompt):
    response_stream = ollama.generate_stream_response(
        prompt,
        history,
        system_prompt,
        "llama-3.2-3b",
        max_tokens=200,
        use_chat=True
    )
    buffer=""
    for event in parse_stream(response_stream):
        print(event)
        if event["type"] == "speech":
            content = event["content"]
            speak_piper(content)
            buffer+=f"{content}\n"
    print(f"\n\nStreaming Response from Ollama:\n{buffer}")
    
def parse_stream(stream):
    buffer = ""
    current_field = None
    for chunk,_,_ in stream:
        buffer += chunk  # Accumulate incoming chunks of text
        
        # Process until we find a complete key-value pair or a period in the 'speech' field
        while buffer:
            if not current_field:  # Detect the key (field name)
                key_start = buffer.find('"')
                if key_start == -1:
                    break
                key_end = buffer.find('"', key_start + 1)
                if key_end == -1:
                    break
                current_field = buffer[key_start + 1:key_end]
                buffer = buffer[key_end + 1:].lstrip()
            else:  # Process the value of the current field
                if buffer.startswith(":"):  # Skip the colon
                    buffer = buffer[1:].lstrip()
                
                if buffer.startswith('"'):  # Handle string value
                    value_start = 1
                    value_end = buffer.find('"', value_start)
                    if value_end == -1:
                        break  # Incomplete value, wait for more data
                    value = buffer[value_start:value_end]
                    buffer = buffer[value_end + 1:].lstrip()
                    
                    if current_field == "speech":  # Handle sentences in the speech field
                        sentences = value.split(". ")
                        for sentence in sentences[:-1]:
                            yield {"type": "speech", "content": sentence.strip() + "."}
                        if sentences[-1]:  # Incomplete sentence
                            buffer = sentences[-1] + buffer
                        current_field = None
                    else:
                        yield {"type": current_field, "content": value}
                        current_field = None
                elif buffer.startswith("{") or buffer.startswith("["):
                    # Skip nested objects/arrays for simplicity
                    stack = [buffer[0]]
                    i = 1
                    while i < len(buffer) and stack:
                        if buffer[i] in "{[":
                            stack.append(buffer[i])
                        elif buffer[i] in "}]":
                            stack.pop()
                        i += 1
                    if not stack:  # Found matching braces
                        value = buffer[:i]
                        buffer = buffer[i:].lstrip()
                        yield {"type": current_field, "content": value}
                        current_field = None
                    else:
                        break  # Incomplete nested object/array
                else:  # Unquoted value (e.g., numbers, booleans)
                    value_end = buffer.find(",")
                    if value_end == -1:
                        break
                    value = buffer[:value_end].strip()
                    buffer = buffer[value_end + 1:].lstrip()
                    yield {"type": current_field, "content": value}
                    current_field = None
    
def parse_stream_chat(stream):
    buffer = ""
    in_action = False
    for token, _, _ in stream:
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
    