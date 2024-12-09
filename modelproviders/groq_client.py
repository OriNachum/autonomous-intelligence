import os
import json
import requests  # Changed from OpenAI import

from dotenv import load_dotenv

class GroqService:
    def __init__(self):
        load_dotenv()  # Load environment variables from .env file
        self.api_key = os.getenv("GROQ_API_KEY")
        if not self.api_key:
            raise ValueError("GROQ_API_KEY environment variable is not set.")
        
        self.api_url = "https://api.groq.com/openai/v1/"  # Groq API base URL
        self.headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }

    def _get_model_id_by_name(self, model):
        model_map = {
            "mixtral": "mixtral-8x7b-32768",
            "haiku": "claude-3-haiku-20240307",
            "sonnet": "claude-3-sonnet-20240229",
            "llama-3.2-3b": "llama-3.2-3b-preview"  # Added required model
            # Add other model mappings if necessary
        }
        return model_map.get(model, model)  # Default model

    def generate_response(self, prompt, history, system_prompt, model, max_tokens=200, use_chat=True):
        endpoint = "chat/completions" if use_chat or history else "completions"
        payload = {
            "model": self._get_model_id_by_name(model),
            "max_tokens": max_tokens
        }
        
        if use_chat:
            messages = history.copy()
            messages.append({"role": "user", "content": prompt})
            if system_prompt:
                messages.insert(0, {"role": "system", "content": system_prompt})
            payload["messages"] = messages
        else:
            payload["prompt"] = f"{system_prompt}\n{prompt}" if system_prompt else prompt
        
        response = requests.post(f"{self.api_url}/chat/completions" if use_chat or history else f"{self.api_url}/completions",
                                 headers=self.headers, json=payload, verify=False)
        if response.status_code != 200:
            raise Exception(f"API request failed with status code {response.status_code}: {response.text}")
        
        output = response.json()
        if use_chat:
            return output.get('choices', [{}])[0].get('message', {}).get('content', '').strip()
        else:
            return output.get('choices', [{}]).get('text', '').strip()

    def generate_stream_response(self, prompt, history, system_prompt, model, use_chat=True, max_tokens=200):
        endpoint = "chat/completions" if use_chat or history else "completions"
        payload = {
            "model": self._get_model_id_by_name(model),
            "max_tokens": max_tokens,
            "stream": True
        }
        
        if use_chat:
            messages = history.copy()
            messages.append({"role": "user", "content": prompt})
            if system_prompt:
                messages.insert(0, {"role": "system", "content": system_prompt})
            payload["messages"] = messages
        else:
            payload["prompt"] = f"{system_prompt}\n{prompt}" if system_prompt else prompt
        
        try:
            response = requests.post(f"{self.api_url}/chat/completions" if use_chat or history else f"{self.api_url}/completions",
                                     headers=self.headers, json=payload, stream=True, verify=False)
            print(f"Status Code: {response.status_code}")
            print(json.dumps(response))
            if response.status_code == 200:
                for line in response.iter_lines():
                    if line:
                        decoded_line = json.loads(line.decode('utf-8'))
                        if 'choices' in decoded_line:
                            choice = decoded_line['choices'][0]
                            if 'delta' in choice and 'content' in choice['delta']:
                                content = choice['delta']['content']
                                print(content, end='', flush=True)
                                yield content
            else:
                print(f"Request failed with status code {response.status_code}")
                print(response.text)
        except requests.exceptions.RequestException as e:
            print(f"An error occurred: {e}")

if __name__ == "__main__":
    service = GroqService()
    prompt = "What is the capital of France?"
    USE_STREAM = False
    # USE_STREAM = True
    USE_CHAT = True  # Hardcoded flag to choose endpoint

    if USE_STREAM:
        print("Streaming Response:")
        for response_part in service.generate_stream_response(
            prompt=prompt,
            history=[],  # Example: [{"role": "user", "content": "Hello"}]
            system_prompt="You are a knowledgeable assistant.",
            model="llama-3.2-3b",
            use_chat=USE_CHAT
        ):
            pass
    else:
        response = service.generate_response(
            prompt=prompt,
            history=[],  # Example: [{"role": "user", "content": "Hello"}]
            system_prompt="You are a knowledgeable assistant.",
            model="llama-3.2-3b",
            use_chat=USE_CHAT
        )
        print(f"Response: {response}")
