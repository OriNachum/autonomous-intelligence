import requests
from requests.structures import CaseInsensitiveDict

def generate_response(prompt, history, system_prompt):
    headers = CaseInsensitiveDict()
    headers["Content-Type"] = "application/json"
    headers["X-API-Key"] = API_KEY
    headers["Transfer-Encoding"] = "chunked"

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

    response = requests.post(
        CHAT_STREAM_API_URL,
        headers=headers,
        json=data,
        stream=True
    )

    response.raise_for_status()

    stream_output = ""
    for chunk in response.iter_content(chunk_size=None):
        stream_output += chunk.decode()
        output_data = stream_output.split("data: ")
        for data_chunk in output_data[1:]:
            message_chunk = data_chunk.split("\n\n")[0]
            if message_chunk:
                message_json = message_chunk + "\n\n"
                print(message_json, end="")

    return stream_output.strip()