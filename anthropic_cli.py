import argparse
import requests
import os
import datetime
from dotenv import load_dotenv
import anthropic

load_dotenv()  # Load environment variables from .env file

API_KEY = os.getenv("ANTHROPIC_API_KEY")
API_URL = "https://api.anthropic.com/v1/complete"
CHAT_API_URL = "https://api.anthropic.com/v1/chat/completions"
HISTORY_FILE = "conversation_history.txt"
SYSTEM_PROMPT_FILE = "prompts/system.md"

if not API_KEY:
    raise ValueError("ANTHROPIC_API_KEY environment variable is not set.")

client = anthropic.Anthropic()

def generate_response(prompt, history, system_prompt, client):
    # headers = {
    #     "Content-Type": "application/json",
    #     "X-API-Key": API_KEY
    # }
    messages = []
    #if system_prompt:
    #    messages.append({"role": "system", "content": system_prompt})
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

    # response = requests.post(CHAT_API_URL, headers=headers, json=data)
    # response.raise_for_status()
    # content = response.json()["response"]["message"]["content"]
    message = client.messages.create(
        # model = "claude-3-opus-20240229",
        model = "claude-3-haiku-20240307",
        messages = messages,
        max_tokens = 1000,
        system = system_prompt
    )
    content = message.content
    return content

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

    response = generate_response(prompt, history, system_prompt, client)
    print(response)
    save_to_history("Assistant", response)