import os
import datetime
import socket
import selectors
from dotenv import load_dotenv
from modelproviders.openai_api_client import OpenAIService
from persistency.direct_knowledge import load_direct_knowledge, add_to_direct_knowledge, save_over_direct_knowledge
from persistency.history import save_to_history, load_history
from services.prompt_service import load_prompt
from assistants.short_term_memory_saver import get_historical_facts, mark_facts_for_deletion
from services.actions_service import extract_actions, is_action_supported, parse_action, execute_action
from services.response_processor import emit_classified_sentences
from services.speech_queue import SpeechQueue
from services.memory_service import MemoryService
import re

load_dotenv()  # Load environment variables from .env file

API_KEY = os.getenv("ANTHROPIC_API_KEY")
HISTORY_FILE = "conversation_history.txt"
SYSTEM_PROMPT_FILE = "prompts/system.md"

if not API_KEY:
    raise ValueError("ANTHROPIC_API_KEY environment variable is not set.")

socket_path = "./sockets/tau_hearing_socket"
sel = selectors.DefaultSelector()

def setup_socket():
    if os.path.exists(socket_path):
        os.remove(socket_path)
    
    sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    sock.bind(socket_path)
    sock.listen(1)
    sel.register(sock, selectors.EVENT_READ, accept)
    return sock

def accept(sock):
    conn, addr = sock.accept()
    sel.register(conn, selectors.EVENT_READ, read)

def read(conn):
    data = conn.recv(1024)
    if data:
        main_tau_loop(data.decode('utf-8'))
    else:
        sel.unregister(conn)
        conn.close()

def get_time_since_last(history):
    last_entry = history.strip().split("\n")[-1]
    timestamp_match = None
    if "[User]" in last_entry:
        return None
    elif "[Assistant]" in last_entry:
        timestamp_match = re.search(r'^(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})', last_entry)
    if timestamp_match:
        timestamp_str = timestamp_match.group(1)
        last_timestamp_obj = datetime.datetime.strptime(timestamp_str, "%Y-%m-%d %H:%M:%S")
        time_since_last = datetime.datetime.now() - last_timestamp_obj
        days = time_since_last.days
        seconds = time_since_last.seconds
        hours = seconds // 3600
        minutes = (seconds % 3600) // 60
        seconds = (seconds % 60)
        time_parts = []
        if days > 0:
            time_parts.append(f"{days} days")
        if hours > 0:
            time_parts.append(f"{hours} hours")
        if minutes > 0:
            time_parts.append(f"{minutes} minutes")
        if seconds > 0 or not time_parts:
            time_parts.append(f"{seconds} seconds")
        return ", ".join(time_parts)
    else:
        return None

def main_tau_loop(user_input):
    speech_queue = SpeechQueue()
    memory_service = MemoryService()
    openai = OpenAIService()
    history = load_history()
    direct_knowledge = load_direct_knowledge()
    tau_system_prompt,_ = load_prompt("tau")
    tau_system_prompt = tau_system_prompt.replace("{{direct_knowledge}}", direct_knowledge)
    model_selector_system_prompt,_ = load_prompt("model-selector")
    print("Conversation History:\n")
    print(history.replace("\\n", "\n"))
    last_entry = history.strip().split("\n")[-1]
    if "[User]" in last_entry:
        prompt = last_entry.split("[User]")[1].strip()
        history = history[:history.rfind("[User]")]
    else:
        time_since_last = get_time_since_last(history)
        raw_prompt = user_input
        current_datetime = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        if time_since_last:
            time_since_last_str = str(time_since_last).split('.')[0]
            prompt_prefix = f"[{current_datetime}][{time_since_last_str}]"
        else:
            print("===== WARNING: No previous timestamp found in the conversation history. =====")
            prompt_prefix = f"[{current_datetime}]"
        if isinstance(raw_prompt, str):
            prompt = f"{prompt_prefix} {raw_prompt}"
            save_to_history("User", prompt)
        else:
            prompt = raw_prompt
            save_to_history("User", f"{prompt_prefix} Here is the photo you have taken *Photo redacted due technical reasons*")
    if isinstance(prompt, str):
        wrapped_prompt = f"Please assess the correct model for the following request, wrapped with double '---' lines: \n---\n---\n{prompt} \n---\n---\n Remember to answer only with one of the following models (haiku, sonnet, opus)"
    else:
        wrapped_prompt = "opus"
    model = "gpt-4o"
    speech_index=0
    response = ""
    speech_queue.reset()
    for text_type,text in emit_classified_sentences(openai.generate_stream_response(prompt,  history, tau_system_prompt, model)):
        if (text is not None) and (text_type is not None):
            print(f"{text_type}: {text}", flush=True)
            response += text
        if text_type == "speech":
            path = f"speech_{speech_index}.mp3"
            speech_index+=1
            path = openai.speechify(text, path)
            if (path is not None):
                speech_queue.enqueue(path)
    save_to_history("Assistant", response)
    print("\n**Finished transmission**\n")
    facts = get_historical_facts()
    facts_string = "\n".join(facts)
    add_to_direct_knowledge(facts_string)
    memory_service.remember_many(facts, "facts")
    deprecated_facts = mark_facts_for_deletion()
    new_facts_string = "\n".join([fact for fact in facts if fact not in deprecated_facts])
    save_over_direct_knowledge(new_facts_string)
    automated_prompt = None
    actions_list = extract_actions(response)
    for action in actions_list:
        parsed_action = parse_action(action, [])
        if is_action_supported(parsed_action):
            automated_prompt = execute_action(parsed_action)
            break
    if automated_prompt is not None:
        next_prompt = automated_prompt
    else:
        next_prompt = input("Wait for the audio to finish. Enter to exit, Reply if you like to respond\n")
        speech_queue.clear()
    return next_prompt

if __name__ == "__main__":
    sock = setup_socket()
    print(f"Listening on {socket_path}")
    try:
        while True:
            events = sel.select()
            for key, mask in events:
                callback = key.data
                callback(key.fileobj)
    except KeyboardInterrupt:
        print("Shutting down.")
    finally:
        sel.close()
        os.remove(socket_path)
