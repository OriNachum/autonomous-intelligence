import os
import requests
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

API_KEY = os.getenv("GROQ_API_KEY")
API_URL = "https://api.groq.com/openai/v1"  # Replace this with the actual Groq API endpoint URL

if not API_KEY:
    raise ValueError("GROQ_API_KEY environment variable is not set.")

HEADERS = {
    "Authorization": f"Bearer {API_KEY}",
    "Content-Type": "application/json"
}

def get_model_id_by_name(model):
    if model == "mixtral":
        return "mixtral-8x7b-32768"
    if model == "haiku":
        return "claude-3-haiku-20240307"
    if model == "sonnet":
        return "claude-3-sonnet-20240229"

def groq_completion(text, history, system_prompt, model):
    model_id = get_model_id_by_name(model)
    messages = []
    if system_prompt:
        messages.append({
            "role": "system",
            "content": system_prompt
        })
    if history:
        for entry in history.split("\n"):
            if "[User]" in entry:
                user_message = entry.split("[User]: ")[1]
                messages.append({"role": "user", "content": user_message})
            elif "[Assistant]" in entry:
                assistant_message = entry.split("[Assistant]: ")[1]
                messages.append({"role": "assistant", "content": assistant_message})

    messages.append({
        "role": "user",
        "content": text
    })

    payload = {
        "messages": messages,
        "model": model_id,
    }

    response = requests.post(f"{API_URL}/chat/completions", json=payload, headers=HEADERS)
    if response.status_code != 200:
        raise Exception(f"API request failed with status code {response.status_code}: {response.text}")

    content = response.json()['choices'][0]['message']['content']  # Adjust based on actual API response structure
    return content

if __name__ == "__main__":
    response = groq_completion("say hello world", "You only respond in UPPERCASE", "Testing system prompt", "mixtral")
    print(response)
