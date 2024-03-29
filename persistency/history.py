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

backward_history_length=20
def load_history():
    if os.path.exists(HISTORY_FILE):
        with open(HISTORY_FILE, "r") as file:
            file_content = file.read()
            file_split = file_content.splitlines() # Split the content into lines
            # Take extra line if ended with user
            total_lines = len(file_split)
            lines_to_take = backward_history_length if total_lines % 2 == 0 else backward_history_length + 1
            return '\n'.join(file_split[-1*lines_to_take:]) # Join and return the last x lines
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
