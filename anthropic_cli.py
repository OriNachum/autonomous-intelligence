import argparse
import requests
import os
import datetime
from dotenv import load_dotenv

load_dotenv()  # Load environment variables from .env file

API_KEY = os.getenv("ANTHROPIC_API_KEY")
API_URL = "https://api.anthropic.com/v1/complete"
CHAT_API_URL = "https://api.anthropic.com/v1/chat/completions"
HISTORY_FILE = "conversation_history.txt"
SYSTEM_PROMPT_FILE = "prompts/system.md"

if not API_KEY:
    raise ValueError("ANTHROPIC_API_KEY environment variable is not set.")

def generate_response(prompt, history, system_prompt):
    headers = {
        "Content-Type": "application/json",
        "X-API-Key": API_KEY
    }
    messages = []
    if system_prompt:
        messages.append({"role": "system", "content": system_prompt})
    if history:
        for entry in history.split("\n"):
            if "[User]" in entry:
                user_message = entry.split("[User]: ")[1]
                messages.append({"role": "user", "content": user_message})
            elif "[Assistant]" in entry:
                assistant_message = entry.split("[Assistant]: ")[1]
                messages.append({"role": "assistant", "content": assistant_message})
    messages.append({"role": "user", "content": prompt})

    data = {
        "messages": messages,
        "max_tokens_to_sample": 1000,
        "stop_sequences": []
    }

    response = requests.post(CHAT_API_URL, headers=headers, json=data)
    response.raise_for_status()
    assistant_response = response.json()["response"]["message"]["content"]
    return assistant_response

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

    parser = argparse.ArgumentParser(description="Simple CLI for Anthropic API")
    parser.add_argument("prompt", nargs="+", help="The prompt to send to the Anthropic API")
    args = parser.parse_args()

    prompt = " ".join(args.prompt)
    save_to_history("User", prompt)

    response = generate_response(prompt, history, system_prompt)
    print(response)
    save_to_history("Assistant", response)