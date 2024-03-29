import re
import os
import sys
from prompt_service import load_prompt
from camera_service import CameraService

if __name__ == "__main__":
    parent_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    if parent_dir not in sys.path:
        sys.path.append(parent_dir)

from modelproviders.groq_client import groq_completion

def extract_actions(text):
    # Extract from the text only * asteriks. Drop to double new line between quotes.
    # Use regex to pull all text within asteriks
    actions = re.findall(r'\*(.+?)\*', text)
    text_str = "\n".join(actions)
    print (text_str)
    return actions

possible_actions = '''
take a picture
'''


def is_action_supported(action):
    return possible_actions.contains(actoin)

classifier_system, classifier_user = load_prompt("action-classifier")
def parse_action(action):
    # Use the Groq model to classify the action
    replaced_user_prompt = classifier_user.replace("<user-request>", action)
    replaced_user_prompt = replaced_user_prompt.replace("<robot-actions>", possible_actions)
    
    parsed_action = groq_completion(replaced_user_prompt, classifier_system, "mixtral")
    return parsed_action

def execute_action(action):
    if (action == 'take a picture'):
        camera = CameraService()
        path = "./image.jpg"
        result = camera.capture_image(path)
        return path
    return None

if __name__ == "__main__":
    actions = extract_actions("Hello, World! \"This is a test\". *Tapping my hat* This should not be spoken. \"This is another test\". *Taking a picture* And here is another test.")
    print(actions)
    for action in actions:
        print(f"starting to parse action: {action}")
        parsed_action = parse_action(action)
        print(parsed_action)
        print('---')
    # Play the audio file, not using ffplay
    
