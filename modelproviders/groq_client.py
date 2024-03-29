import os

from groq import Groq
from dotenv import load_dotenv

load_dotenv()  # Load environment variables from .env file

API_KEY = os.getenv("GROQ_API_KEY")

if not API_KEY:
    raise ValueError("GROQ_API_KEY environment variable is not set.")



client = Groq(
    api_key=os.environ.get("GROQ_API_KEY"),
)

def _get_model_id_by_name(model):
  if model == "mixtral":
    return "mixtral-8x7b-32768"
  if model == "haiku":
    return "claude-3-haiku-20240307"
  if model == "sonnet":
    return "claude-3-sonnet-20240229"



def groq_completion(text, history, system_prompt, model):
    model_id = _get_model_id_by_name(model)
    messages = []
    if (system_prompt):
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
    chat_completion = client.chat.completions.create(
        messages=messages,
        model=model_id,
    )
    return chat_completion.choices[0].message.content

if "__main__" == __name__:
  response = groq_completion("say hello world", "You only respond in UPPERCASE", "mixtral")
  print(response)
