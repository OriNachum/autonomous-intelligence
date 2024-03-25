import sys
import os

if __name__ == "__main__":
    parent_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    if parent_dir not in sys.path:
        sys.path.append(parent_dir)
        
from persistency.local_file import load_history
from modelproviders.anthropic_client import generate_response
from services.prompt_service import load_prompt

def prepare_prompts():
    history = load_history()
    system_prompt, user_prompt  = load_prompt("short-term-memory-saver")
    return system_prompt, user_prompt, history


def get_historical_facts():
    print("Conversation History:\n")
    system_prompt, user_prompt, history = prepare_prompts()
    response = generate_response(user_prompt , history, system_prompt, "sonnet")
    # take all lines that start with -
    response = "\n".join([line for line in response.split("\n") if line.startswith("-")])
    return response
if __name__ == "__main__":
    response = get_historical_facts()
    print(response)
