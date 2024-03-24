import os
import datetime
from dotenv import load_dotenv
from modelproviders.anthropic_client import generate_response
from persistency.local_file import save_to_history, load_history
import re
load_dotenv()  # Load environment variables from .env file

API_KEY = os.getenv("ANTHROPIC_API_KEY")
HISTORY_FILE = "conversation_history.txt"
SYSTEM_PROMPT_FILE = "prompts/system.md"

if not API_KEY:
    raise ValueError("ANTHROPIC_API_KEY environment variable is not set.")

def load_prompt(name):
    system_prompt_file = f"./prompts/{name}/{name}.system.md"
    if os.path.exists(system_prompt_file):
        with open(system_prompt_file, "r") as file:
            return file.read()
    else:
        return ""

# prefix examples
# If there is a previous timestamp: [2023-05-01 14:30:00][0:03:12] What is the capital of France?
# If there is no previous timestamp: [2023-05-01 14:30:00] What is the capital of France?
def get_time_since_last(history):
    # Get the last entry's timestamp from the history
    last_entry = history.strip().split("\n")[-1]

    timestamp_match = None
    if "[User]" in last_entry:
        timestamp_match = re.search(r'\[([\d\-: ]+)\]', last_entry)
    elif "[Assistant]" in last_entry:
        timestamp_match = re.search(r'\[([\d\-: ]+)\]', last_entry)

    if timestamp_match:
        timestamp_str = timestamp_match.group(1)

        # Convert the timestamp string to a datetime object
        last_timestamp_obj = datetime.datetime.strptime(timestamp_str, "%Y-%m-%d %H:%M:%S")

        # Calculate the time since the last correspondence
        time_since_last = datetime.datetime.now() - last_timestamp_obj

        return time_since_last
    else:
        return None

if __name__ == "__main__":
    history = load_history()
    main_system_prompt = load_prompt("main")
    model_selector_system_prompt = load_prompt("model-selector")
    print("Conversation History:\n")
    print(history)
    
    # Get from history last prompt:
    # If it is a user prompt, use it as a prompt for the assistant
    # If it is an assistant prompt, ask for a new prompt
    last_entry = history.strip().split("\n")[-1]
    if "[User]" in last_entry:
        prompt = last_entry.split("[User]")[1].strip()
        # remove last entry from history:
        history = history[:history.rfind("[User]")]
    else:
        # Request for a prompt
        raw_prompt = input(f"Please enter a prompt: ")
        time_since_last = get_time_since_last(history)

        current_datetime = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        if time_since_last:
            time_since_last_str = str(time_since_last).split('.')[0]
            prompt_prefix = f"[{current_datetime}][{time_since_last_str}]"
        else:
            prompt_prefix = f"[{current_datetime}]"

        prompt = f"{prompt_prefix} {raw_prompt}"
        save_to_history("User", prompt)

    #response = generate_response(prompt, history, system_prompt, "haiku")
    response = generate_response(prompt, history, model_selector_system_prompt, "sonnet")
    print(f"Selected {response}")
    response = generate_response(prompt, history, main_system_prompt, response)
    print(response)
    save_to_history("Assistant", response)
