import os

from groq import Groq

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



def groq_completion(text, system_prompt, model):
    model_id = _get_model_id_by_name(model)
    messages = []
    if (system_prompt):
        messages.append({
            "role": "system",
            "content": system_prompt
        })
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
