import re
import os
import sys
import base64

if __name__ == "__main__":
    parent_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    if parent_dir not in sys.path:
        sys.path.append(parent_dir)

from services.prompt_service import load_prompt
from services.camera_service_wrapper import capture_image


from modelproviders.groq_api_client import groq_completion

def extract_actions(text):
    # Extract from the text only * asteriks. Drop to double new line between quotes.
    # Use regex to pull all text within asteriks
    actions = re.findall(r'\*(.+?)\*', text)
    text_str = "\n".join(actions)
    
    return actions

possible_actions = '''
take a picture
'''


def is_action_supported(action):
    return action in possible_actions

classifier_system, classifier_user = load_prompt("action-classifier")
def parse_action(action, history):
    # Use the Groq model to classify the action
    replaced_user_prompt = classifier_user.replace("<user-request>", action)
    replaced_user_prompt = replaced_user_prompt.replace("<robot-actions>", possible_actions)
    
    parsed_action = groq_completion(replaced_user_prompt, history, classifier_system, "mixtral")
    return parsed_action

def execute_action(action):
    if (action == 'take a picture'):
        path = "./image.jpg"
        capture_image(path)
        with open(path, "rb") as file:
            image_bytes = file.read()
            image_encoded = base64.b64encode(image_bytes).decode("utf-8")
            request = [
                {
                    "type": "image",
                    "source": {
                        "type": "base64",
                        "media_type": "image/jpeg",
                        "data": image_encoded
                    }
                },
                {
                    "type": "text",
                    "text": "Here is the photo you have taken. What you see in the image is what's in front of you. This is what you see from your Nvidia Jetson Nano Developer Kit body and camera module."
                }
            ]
            return request
    return None

if __name__ == "__main__":
    actions = extract_actions("Hello, World! \"This is a test\". *Tapping my hat* This should not be spoken. \"This is another test\". *Taking a picture* And here is another test.")
    actions = ["takes another picture utilizing the integrated camera hardware"]
    print(actions)
    for action in actions:
        print(f"starting to parse action: {action}")
        parsed_action = parse_action(action, [])
        print(parsed_action)
        print('---')
    # Play the audio file, not using ffplay
    
