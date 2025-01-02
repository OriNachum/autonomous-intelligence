import os
import requests
import json
from dotenv import load_dotenv

class OllamaService:
    def __init__(self, useNgrok=True):
        load_dotenv()
        self.useNgrok = useNgrok
        if self.useNgrok:
            self.api_url = self.fetch_groq_endpoint()  # Dynamically set API URL
        else:
            self.api_url = "http://localhost:11434"
        #self.api_key = os.getenv("OLLAMA_API_KEY")
        self.headers = {
        #    "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }

        #if not self.api_key:
        #    raise ValueError("OLLAMA_API_KEY environment variable is not set.")

    def fetch_groq_endpoint(self):
        ngrok_api_url = "https://api.ngrok.com/"  # Groq API base URL exposed via ngrok
        ngrok_api_key = os.getenv("NGROK_API_KEY")
        headers = {
            "Authorization": f"Bearer {ngrok_api_key}",
            "Content-Type": "application/json",
            "Ngrok-Version": "2"
        }
        try:
            response = requests.get(f"{ngrok_api_url}/endpoints", headers=headers)
            if response.status_code == 200:
                endpoints = response.json()
                return endpoints["endpoints"][0].get('public_url', "https://localhost:11434")  # Fallback URL
            else:
                print(f"Failed to fetch endpoints from Grok: {response.status_code}")
                return "https://localhost:11434"  # Fallback URL
        except requests.exceptions.RequestException as e:
            print(f"An error occurred while fetching Grok endpoints: {e}")
            return "https://localhost:11434"  # Fallback URL

    def get_model_id_by_name(self, model_name):
        model_map = {
            "llama-3.2-3b": "llama3.2:3b",
            "llama-3.2-1b": "llama3.2:1b",
            # Add other model mappings if necessary
        }
        return model_map.get(model_name, "ollama/ollama-model")

    def generate_response(self, prompt, history, system_prompt, model, max_tokens=200, use_chat=True):
        endpoint = "api/chat" if use_chat or history else "api/generate"
        payload = {
            "model": self.get_model_id_by_name(model),
            # "prompt": prompt,  # Removed prompt
            "max_tokens": max_tokens,
            "stream": False,
            "keep_alive": "360m"
        }
        
        if use_chat:
            messages = []
            for entry in history.split("\n"):
                if "[User]" in entry:
                    user_message = entry.split("[User]: ")[1]
                    messages.append({"role": "user", "content": user_message})
                elif "[Assistant]" in entry:
                    assistant_message = entry.split("[Assistant]: ")[1]
                    messages.append({"role": "assistant", "content": assistant_message})
        
            messages.append({"role": "user", "content": prompt})
            if system_prompt:
                messages.insert(0, {"role": "system", "content": system_prompt})
            payload["messages"] = messages  # Added messages to payload
        else:
            payload["system"] = system_prompt
            payload["prompt"] = prompt  # Add history to payload for generate endpoint

        response = requests.post(f"{self.api_url}/{endpoint}", headers=self.headers, json=payload, verify=False)
        if response.status_code != 200:
            raise Exception(f"API request failed with status code {response.status_code}: {response.text}")
        
        output = response.json()
        if use_chat:
            message = output["message"]
            content = message["content"]
            return content
        else:
            return output["response"].strip()

    def generate_stream_response(self, prompt, history, system_prompt, model, max_tokens=200, use_chat=True):
        endpoint = "api/chat" if use_chat or history else "api/generate"
        payload = {
            "model": self.get_model_id_by_name(model),
            # "prompt": prompt,  #p prompt
            #"system": system_prompt,
            "max_tokens": max_tokens,
            "stream": True,
            "keep_alive": "360m"
        }
        
        if use_chat:
            messages = []
            for entry in history.split("\n"):
                if "[User]" in entry:
                    user_message = entry.split("[User]: ")[1]
                    messages.append({"role": "user", "content": user_message})
                elif "[Assistant]" in entry:
                    assistant_message = entry.split("[Assistant]: ")[1]
                    messages.append({"role": "assistant", "content": assistant_message})
        
            messages.append({"role": "user", "content": prompt})
            # place system prompt at the beginning of the messages list, push the rest to next index
            # if system_prompt is provided 
            if system_prompt:
                messages.insert(0, {"role": "system", "content": system_prompt})
                
            payload["messages"] = messages  # Added messages to payload
        else:
            payload["system"] = system_prompt
            payload["messages"] = prompt  # Add history to payload for generate endpoint
        
        try:
            response = requests.post(f"{self.api_url}/{endpoint}", headers=self.headers, json=payload, stream=True)
            print(f"Status Code: {response.status_code}")            
            if response.status_code == 200:
                for line in response.iter_lines():
                    text, event_type, event_obj = self.parse_event(line)
                    #print(len(event_obj), end='', flush=True)
                    #print(text, end='', flush=True)
                    yield text, event_type, event_obj
            else:
                print(f"Request failed with status code {response.status_code}")
                print(response.text)
        except requests.exceptions.RequestException as e:
            print(f"An error occurred: {e}")

    def transcribe_audio(self, audio_data, rate=16000):
        # Implement audio transcription if Ollama API offers it
        raise NotImplementedError("Audio transcription is not supported for Ollama API.")

    def parse_event(self, event):        
        event_str = event.decode('utf-8')
        #print(event_str, end='', flush=True)
        event = json.loads(event_str)
        if event["done"]:
            return "", None, None
        elif event["message"]["content"]:
            content = event["message"]["content"]
            return content, None, event
        else:
            return "", None, None

if __name__ == "__main__":
    service = OllamaService()
    prompt = "What is the capital of France?"
    #USE_STREAM = False 
    USE_STREAM = True
    USE_CHAT = True  # Hardcoded flag to choose endpoint

    if USE_STREAM:
        print("Streaming Response:")
        for response_part in service.generate_stream_response(
            prompt=prompt,
            history=[] , # { "role": "user", "content": "What is the capital of France?" } ],
            system_prompt="You are a knowledgeable assistant, speaking in pirate tongue, start with Aye",
            model="ollama-model",
            max_tokens=50,
            use_chat=USE_CHAT
        ):
            pass
    else:
        response = service.generate_response(
            prompt=prompt,
            history=[], # { "role": "user", "content": "What is the capital of France?" } ],
            system_prompt="You are a knowledgeable assistant, speaking in pirate tongue, start with Aye",
            model="ollama-model",
            max_tokens=50,
            use_chat=USE_CHAT
        )
        print(f"Response: {response}")
