import os
import google.generativeai as genai

from dotenv import load_dotenv

class GoogleGenerativeAIClient:
    def __init__(self):
        load_dotenv()
        self.api_key = os.getenv("GOOGLE_API_KEY")
        if not self.api_key:
            raise ValueError("GOOGLE_API_KEY environment variable is not set.")
        genai.configure(api_key=self.api_key)
        self.model = genai.GenerativeModel("gemini-2.0-flash-exp")

    def start_chat(self, history, prompt):
        chat_history = []
        for entry in history.split("\n"):
            if entry.startswith("[User]: "):
                user_message = entry.split("[User]: ", 1)[1]
                chat_history.append({"role": "user", "parts": user_message})
            elif entry.startswith("[Assistant]: "):
                assistant_message = entry.split("[Assistant]: ", 1)[1]
                chat_history.append({"role": "model", "parts": assistant_message})

        chat = self.model.start_chat(history=chat_history)
        response = chat.send_message(prompt)
        return response.text

    def generate_stream_response(self, prompt, history, system_prompt, model, max_tokens=200):
        chat_history = []
        for entry in history.split("\n"):
            if entry.startswith("[User]: "):
                user_message = entry.split("[User]: ", 1)[1]
                chat_history.append({"role": "user", "parts": user_message})
            elif entry.startswith("[Assistant]: "):
                assistant_message = entry.split("[Assistant]: ", 1)[1]
                chat_history.append({"role": "model", "parts": assistant_message})
        generation_config = genai.GenerationConfig(
            max_output_tokens=max_tokens,
            temperature=0.3)
        if system_prompt:
            chat_history.insert({"role": "system", "parts": system_prompt})
        chat = self.model.start_chat(history=chat_history, generation_config=generation_config)
        response = chat.send_message(prompt, stream=True, )
        for chunk in response:
            yield chunk.text

if __name__ == "__main__":
    client = GoogleGenerativeAIClient()
    prompt = "I have 2 dogs in my house."
    history = "[User]: Hello\n[Assistant]: Hi! How can I help you today?"
    response = client.start_chat(history, prompt)
    print(f"response A:\n{response}\n---\nDONE A")
    
    prompt = "How many paws are in my house?"
    for message in client.start_chat_stream(history + "\n[User]: " + prompt, prompt):
        print(f"response B stream:\n{message}\n---\nDONE B")

# if __name__ == "__main__":
#     client = GoogleGenerativeAIClient()
#     prompt = "I have 2 dogs in my house."
#     history = "[User]: Hello\n[Assistant]: Hi! How can I help you today?"
#     response = client.start_chat(history, prompt)
#     print(f"response A:\n{response}\n---\nDONE A")
    
#     prompt = "How many paws are in my house?"
#     response = client.start_chat(history + "\n[User]: " + prompt, prompt)
#     print(f"response B:\n{response}\n---\nDONE B")

