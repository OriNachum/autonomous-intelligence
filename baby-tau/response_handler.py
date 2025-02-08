import json
import re
from kokoro_pytorch_speaker import KokoroPytorchSpeaker  # Updated import

class ResponseHandler:
    def __init__(self):
        self.speaker = KokoroPytorchSpeaker()  # Initialize Speaker

    def process_ollama_response(self, ollama, prompt, history, system_prompt):
        response_stream = ollama.generate_stream_response(
            prompt,
            history,
            system_prompt,
            "llama-3.2-3b",
            max_tokens=200,
            use_chat=True
        )
        buffer=""
        for event in self.parse_stream(response_stream):
            print(event, flush=True)
            if event["type"] == "speech":
                content = event["content"].replace("\"", "")
                self.speaker.speak(content)  # Updated call
                buffer += f"{content}\n"
        #print(f"\n\nStreaming Response from Ollama:\n{buffer}")

    def _split_into_sentences(self, text):
        """Split text into sentences, handling edge cases."""
        sentences = re.split(r'(?<=[.!?])(?=\s|$)', text)
        return [s.strip() for s in sentences if s.strip()]

    def parse_stream(self, response_stream):
        """Parse LLM token stream and yield events."""
        buffer = ""
        
        for token,_,_ in response_stream:
            buffer += token
            
            # Try to find complete JSON objects
            while True:
                try:
                    # Find the end of a JSON object
                    end = buffer.find("}")
                    if end == -1:
                        break
                        
                    # Extract potential JSON object
                    obj_str = buffer[:end + 1]
                    
                    try:
                        event = json.loads(obj_str)
                        
                        # Valid JSON object found
                        if "speech" in event:
                            yield {
                                "type": "speech",
                                "content": event["speech"]
                            }
                        elif "thinking" in event:
                            yield {
                                "type": "thinking",
                                "content": event["thinking"]
                            }
                        elif "action" in event:
                            yield {
                                "type": "action",
                                "content": event["action"]
                            }
                        
                        # Remove processed object from buffer
                        buffer = buffer[end + 1:].lstrip()
                        
                    except json.JSONDecodeError:
                        # Not a complete/valid JSON object yet
                        break
                        
                except Exception as e:
                    # Any other error, skip this token
                    print(f"Error processing token: {e}")
                    break

        
    def parse_stream_chat(self, stream):
        buffer = ""
        in_action = False
        for token, _, _ in stream:
            #buffer += token
            in_action_changed = False
            if token == "*":
                in_action = not in_action
                in_action_changed = True
            if not in_action:
                buffer += token
            if "." in token or (in_action_changed and not in_action):
                print(buffer, flush=True)
                speak(buffer)
                buffer = ""


# Example usage
if __name__ == "__main__":
    # Simulate LLM token stream
    test_input = '''{
  "speech": "Okay, here's one: Why couldn't the bicycle stand up by itself?"
}
{
  "thinking": "Generating a punchline..."
}
{
  "speech": "Because it was two-tired!"
}
{
  "action": "displaying a smiley face on screen"
}
{
  "speech": "Hope that made you laugh! Do you want to hear another one?"
}'''
    
    # Split into tokens to simulate streaming
    test_stream = [char for char in test_input]
    handler = ResponseHandler()
    buffer = ""
    for event in handler.parse_stream(test_stream):
        print(event, flush=True)
        if event["type"] == "speech":
            content = event["content"].replace("\"", "")
            buffer += f"{content}\n"
    print(f"\n\nStreaming Response from Ollama:\n{buffer}")
