import requests
import os
import json
import re
from dotenv import load_dotenv
#from contextlib import contextmanager

# Load environment variables from .env file
load_dotenv()

API_KEY = os.getenv("ANTHROPIC_API_KEY")
API_URL = "https://api.anthropic.com/v1"  # Replace with the actual API URL

if not API_KEY:
    raise ValueError("ANTHROPIC_API_KEY environment variable is not set.")

HEADERS = {
    "x-api-key": API_KEY,
    "anthropic-version": "2023-06-01",
    "Content-Type": "application/json"
}

def get_model_id_by_name(model):
    if model == "opus":
        return "claude-3-opus-20240229"
    if model == "haiku":
        return "claude-3-haiku-20240307"
    if model == "sonnet":
        return "claude-3-sonnet-20240229"

def generate_response(prompt, history, system_prompt, model, max_tokens=200):
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
    content = content_block['content'][0]['text']  # Adjust this line based on the actual structure of the API response
    return content

def generate_stream_response(prompt, history, system_prompt, model, max_tokens=200):
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
        "system": system_prompt,
        "stream": True
    }

    with requests.Session() as session:
        response = requests.post(f"{API_URL}/messages", json=payload, headers=HEADERS, stream=True)
        
        for event in response.iter_lines():
            if event:
                event_object = parse_event(event)
                
                yield event_object

def parse_event(event):
    event_string = event.decode()
    # Define regular expression pattern for extracting the event section
    event_pattern = re.compile(r'event:\s*(.*?)(?=data:|$)', re.DOTALL)

    # Search for the event section
    event_match = event_pattern.search(event_string)

    # Extract event content if found
    event_type = event_match.group(1).strip() if event_match else None
    event_content = event_string.replace(f"event: {event_type}", "").replace("data: ", "")
    event_content_object = None
    if (event_content):
        event_content_object = json.loads(event_content)
    #event_json = json.loads(event_string)

    return event_string, event_type, event_content_object


if __name__ == "__main__":
    history = ""
    system_prompt = "testing client"

    prompt = input("Make a request: ")

    response = ""
    model = "opus"
    for event, _, event_content in generate_stream_response(prompt, history, system_prompt, model):
        if event_content and event_content["type"] == "content_block_delta":
            text = event_content["delta"]["text"]
            print(text, end="", flush=True)
    
