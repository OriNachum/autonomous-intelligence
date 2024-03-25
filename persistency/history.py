import os
import datetime

HISTORY_FILE = "conversation_history.txt"

def save_to_history(role, message):
    timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    # normalized message, no newlines
    message = message.replace("\n", "\\n")
    history_entry = f"{timestamp} [{role}]: {message}"
    with open(HISTORY_FILE, "a") as file:
        file.write(history_entry + "\n")

def load_history():
    if os.path.exists(HISTORY_FILE):
        with open(HISTORY_FILE, "r") as file:
            return file.read()
    else:
        return ""

if __name__ == "__main__":
    history = load_history()
    print("Conversation History:\n")
    print(history)
    print("\n")

    # Request for a prompt
    save_to_history("User", "test")

    history = load_history()	
    print("After addition:\n")
    print(history)
