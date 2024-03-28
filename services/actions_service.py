import re

def extract_actions(text):
    # Extract from the text only * asteriks. Drop to double new line between quotes.
    # Use regex to pull all text within asteriks
    text = re.findall(r'\*(.+?)\*', text)
    text = "\n".join(text)
    print (text)

def is_action_supported(action):
    return False    

def parse_action():
    return None

def execute_action():
    return None

if __name__ == "__main__":
    path = extract_actions("Hello, World! \"This is a test\". *Tapping my hat* This should not be spoken. \"This is another test\". *Taking a picture* And here is another test.")
    # Play the audio file, not using ffplay
    