import os
import datetime
from dotenv import load_dotenv
from modelproviders.anthropic_client import generate_response
from persistency.direct_knowledge import load_direct_knowledge, save_over_direct_knowledge
from persistency.history import save_to_history, load_history
from services.prompt_service import load_prompt
from assistants.short_term_memory_saver import get_historical_facts
from services.actions_service import extract_actions, is_action_supported, parse_action, execute_action
import re

from services.speechify import play_mp3, speechify
load_dotenv()  # Load environment variables from .env file

API_KEY = os.getenv("ANTHROPIC_API_KEY")
HISTORY_FILE = "conversation_history.txt"
SYSTEM_PROMPT_FILE = "prompts/system.md"

if not API_KEY:
    raise ValueError("ANTHROPIC_API_KEY environment variable is not set.")

# prefix examples
# If there is a previous timestamp: [2023-05-01 14:30:00][0:03:12] What is the capital of France?
# If there is no previous timestamp: [2023-05-01 14:30:00] What is the capital of France?
def get_time_since_last(history):
    # Get the last entry's timestamp from the history
    last_entry = history.strip().split("\n")[-1]

    timestamp_match = None
    if "[User]" in last_entry:
        return None
    elif "[Assistant]" in last_entry:
        #ßtimestamp_match = re.search(r'\[([\d\-: ]+)\]', last_entry)
        timestamp_match = re.search(r'^(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})', last_entry)

    if timestamp_match:
        timestamp_str = timestamp_match.group(1)
        last_timestamp_obj = datetime.datetime.strptime(timestamp_str, "%Y-%m-%d %H:%M:%S")
        time_since_last = datetime.datetime.now() - last_timestamp_obj

        # Decomposing the time difference
        days = time_since_last.days
        seconds = time_since_last.seconds
        hours = seconds // 3600
        minutes = (seconds % 3600) // 60
        seconds = (seconds % 60)

        # Constructing the textual representation
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
    history = load_history()
    direct_knowledge = load_direct_knowledge()
    tau_system_prompt,_ = load_prompt("tau")
    tau_system_prompt = tau_system_prompt.replace("{{direct_knowledge}}", direct_knowledge)
    model_selector_system_prompt,_ = load_prompt("model-selector")
    print("Conversation History:\n")
    print(history.replace("\\n", "\n"))
    
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
        time_since_last = get_time_since_last(history)
        if (user_input is None or user_input == ""):
            raw_prompt = input(f"Please enter a prompt ({time_since_last}): ")
        else:
            raw_prompt = user_input
        time_since_last = get_time_since_last(history)

        current_datetime = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        if time_since_last:
            time_since_last_str = str(time_since_last).split('.')[0]
            prompt_prefix = f"[{current_datetime}][{time_since_last_str}]"
        else:
            print("===== WARNING: No previous timestamp found in the conversation history. =====")
            prompt_prefix = f"[{current_datetime}]"

        prompt = f"{prompt_prefix} {raw_prompt}"
        save_to_history("User", prompt)

    #response = generate_response(prompt, history, system_prompt, "haiku")
    wrapped_prompt = f"Please assess the correct model for the following request, wrapped with double '---' lines: \n---\n---\n{prompt} \n---\n---\n Remember to answer only with one of the following models (haiku, sonnet, opus)"
    response = generate_response(wrapped_prompt, history, model_selector_system_prompt, "sonnet", max_tokens=10)
    response = response.replace('---', "").replace("\n", "")
    print(f"Selected {response}")
    # If provided with more than 1 word, take the first word as the model name
    if " " in response:
        response = response.split(" ")[0]
    response = generate_response(prompt, history, tau_system_prompt, response)
    print(response)
    save_to_history("Assistant", response)
    print("\n")
    facts = get_historical_facts()
    save_over_direct_knowledge(facts)
    path = speechify(response)
    play_mp3(path)
    action_results = []
    actions_list = extract_actions(response)
    for action in actions_list:
        if is_action_supported(action):
            parsed_action = parse_action(action)
            action_result = execute_action(parsed_action)
            action_results.append(action_result)
    if (actions_list != []):
        # append action results as a new prompt=appended 
        next_prompt = " ".join(action_results) # Requires preparing the image and placing it correcly in the request
        
    else:
        next_prompt = input("Wait for the audio to finish. Enter to exit, Reply if you like to respond\n")
    return next_prompt

if __name__ == "__main__":
    user_input = None
    while (user_input != ""):
        user_input = main_tau_loop(user_input)
        
