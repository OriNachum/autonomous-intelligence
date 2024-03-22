import argparse
import requests
import os
import datetime
from dotenv import load_dotenv
from modelproviders.anthropic_client import generate_response

load_dotenv()  # Load environment variables from .env file

API_KEY = os.getenv("ANTHROPIC_API_KEY")
API_URL = "https://api.anthropic.com/v1/complete"
CHAT_API_URL = "https://api.anthropic.com/v1/chat/completions"
HISTORY_FILE = "conversation_history.txt"
SYSTEM_PROMPT_FILE = "prompts/system.md"

if not API_KEY:
    raise ValueError("ANTHROPIC_API_KEY environment variable is not set.")


def save_to_history(role, message):
    timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    history_entry = f"{timestamp} [{role}]: {message}"
    with open(HISTORY_FILE, "a") as file:
        file.write(history_entry + "\n")

def load_history():
    if os.path.exists(HISTORY_FILE):
        with open(HISTORY_FILE, "r") as file:
            return file.read()
    else:
        return ""

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
