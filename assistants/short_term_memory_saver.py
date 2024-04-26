import sys
import os

if __name__ == "__main__":
    parent_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    if parent_dir not in sys.path:
        sys.path.append(parent_dir)
        
from persistency.history import load_history
from persistency.direct_knowledge import load_direct_knowledge
from modelproviders.anthropic_api_client import generate_response
from services.prompt_service import load_prompt

def _prepare_prompts(assistant_name):
    history = load_history()
    known_facts = load_direct_knowledge()
    system_prompt, user_prompt  = load_prompt(assistant_name)
    user_prompt = user_prompt.replace("<known_facts>", known_facts)
    return system_prompt, user_prompt, history


def get_historical_facts():
    system_prompt, user_prompt, history = _prepare_prompts("short-term-memory-saver")
    response = generate_response(user_prompt , history, system_prompt, "sonnet")
    # take all lines that start with -
    response = [line for line in response.split("\n") if line.startswith("-")]
    return response
    
def mark_facts_for_deletion():    
    system_prompt, user_prompt, history = _prepare_prompts("short-term-memory-clearer")
    response = generate_response(user_prompt , history, system_prompt, "sonnet")
    # take all lines that start with -
    response = [line for line in response.split("\n") if line.startswith("-")]
    return response


if __name__ == "__main__":
    response = get_historical_facts()
    print(response)
