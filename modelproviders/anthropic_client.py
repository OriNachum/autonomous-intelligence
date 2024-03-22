import requests
import os
import datetime
from dotenv import load_dotenv
import anthropic

load_dotenv()  # Load environment variables from .env file

API_KEY = os.getenv("ANTHROPIC_API_KEY")
SYSTEM_PROMPT_FILE = "prompts/system.md"

if not API_KEY:
    raise ValueError("ANTHROPIC_API_KEY environment variable is not set.")

client = anthropic.Anthropic()

def get_model_id_by_name(model):
  if model == "opus":
    return "claude-3-opus-20240229"
  if model == "haiku":
    return "claude-3-haiku-20240307"
  if model == "sonnet":
    return "claude-3-sonnet-20240229"

def generate_response(prompt, history, system_prompt, model):
    model_id = get_model_id_by_name(model)
    messages = []
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

    message = client.messages.create(
        model = model_id,
        messages = messages,
        max_tokens = 1000,
        system = system_prompt
    )
    content_block = message.content
    content = content_block[0].text
    return content


if __name__ == "__main__":
    history = ""
    system_prompt = "testing client"

    prompt = input("Make a request")

    model = "haiku"
    response = generate_response(prompt, history, system_prompt, model)
    print(response)
