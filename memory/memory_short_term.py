import sys
import os

if __name__ == "__main__":
    parent_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    if parent_dir not in sys.path:
        sys.path.append(parent_dir)
        
from persistency.history import load_history
from persistency.direct_knowledge import load_direct_knowledge
#from modelproviders.anthropic_api_client import generate_response
from modelproviders.openai_api_client import OpenAIService
from services.prompt_service import load_prompt

class MemoryShortTerm:
    def __init__(self):
        pass

    def _prepare_prompts(self, assistant_name):
        history = load_history()
        known_facts = load_direct_knowledge()
        system_prompt, user_prompt  = load_prompt(assistant_name)
        user_prompt = user_prompt.replace("<known_facts>", known_facts)
        return system_prompt, user_prompt, history

    def get_historical_facts(self):
        openai = OpenAIService()
        system_prompt, user_prompt, history = self._prepare_prompts("short-term-memory-saver")
        response = openai.generate_response(user_prompt , history, system_prompt, "gpt-4o")
        # take all lines that start with -
        response = [line for line in response.split("\n") if line.startswith("-")]
        return response
    
    def mark_facts_for_deletion(self):    
        openai = OpenAIService()
        system_prompt, user_prompt, history = self._prepare_prompts("short-term-memory-clearer")
        response = openai.generate_response(user_prompt , history, system_prompt, "gpt-4o")
        # take all lines that start with -
        response = [line for line in response.split("\n") if line.startswith("-")]
        return response


if __name__ == "__main__":
    memory_short_term = MemoryShortTerm()
    response = memory_short_term.get_historical_facts()
    print(response)
