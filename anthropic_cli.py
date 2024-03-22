import argparse
import requests
import os
import datetime
from dotenv import load_dotenv
from modelproviders.anthropic_client import generate_response
from persistency.local_file import save_to_history, load_history

load_dotenv()  # Load environment variables from .env file

API_KEY = os.getenv("ANTHROPIC_API_KEY")
HISTORY_FILE = "conversation_history.txt"
SYSTEM_PROMPT_FILE = "prompts/system.md"

if not API_KEY:
    raise ValueError("ANTHROPIC_API_KEY environment variable is not set.")


def load_system_prompt():
    if os.path.exists(SYSTEM_PROMPT_FILE):
        with open(SYSTEM_PROMPT_FILE, "r") as file:
            return file.read()
    else:
        return ""

if __name__ == "__main__":
    history = load_history()
    system_prompt = load_system_prompt()
    print("Conversation History:\n")
    print(history)

    # Request for a prompt
    prompt = input("Please enter a prompt: ")
    save_to_history("User", prompt)

    response = generate_response(prompt, history, system_prompt, "haiku")
    print(response)
    save_to_history("Assistant", response)
