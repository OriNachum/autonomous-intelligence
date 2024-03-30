import requests
import os
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

API_KEY = os.getenv("ANTHROPIC_API_KEY")
API_URL = "https://api.anthropic.com/v1"  # Replace with the actual API URL

if not API_KEY:
    raise ValueError("ANTHROPIC_API_KEY environment variable is not set.")

HEADERS = {
    "Authorization": f"Bearer {API_KEY}",
    "Content-Type": "application/json"
}

def get_model_id_by_name(model):
    if model == "opus":
        return "claude-3-opus-20240229"
    if model == "haiku":
        return "claude-3-haiku-20240307"
    if model == "sonnet":
        return "claude-3-sonnet-20240229"

def generate_response(prompt, history, system_prompt, model, max_tokens=1000):
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

    payload = {
        "model": model_id,
        "messages": messages,
        "max_tokens": max_tokens,
        "system": system_prompt
    }

    response = requests.post(f"{API_URL}/messages", json=payload, headers=HEADERS)
    if response.status_code != 200:
        raise Exception(f"API request failed with status code {response.status_code}: {response.text}")
    
    content_block = response.json()
    content = content_block['choices'][0]['text']  # Adjust this line based on the actual structure of the API response
    return content


if __name__ == "__main__":
    history = ""
    system_prompt = "testing client"

    prompt = input("Make a request: ")

    model = "haiku"
    response = generate_response(prompt, history, system_prompt, model)
    print(response)
