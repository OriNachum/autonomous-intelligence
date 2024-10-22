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

def get_time_since_last(history):
    logger.debug("Calculating time since last interaction")
    last_entry = history.strip().split("\n")[-1]
    timestamp_match = None
    if "[User]" in last_entry:
        logger.debug("Last entry was from User, no time calculation needed")
        return None
    elif "[Assistant]" in last_entry:
        timestamp_match = re.search(r'^(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})', last_entry)
    if timestamp_match:
        timestamp_str = timestamp_match.group(1)
        last_timestamp_obj = datetime.strptime(timestamp_str, "%Y-%m-%d %H:%M:%S")
        time_since_last = datetime.now() - last_timestamp_obj
        days = time_since_last.days
        seconds = time_since_last.seconds
        hours = seconds // 3600
        minutes = (seconds % 3600) // 60
        seconds = (seconds % 60)
        time_parts = []
        if days > 0:
            time_parts.append(f"{days} days")
        if hours > 0:
            time_parts.append(f"{hours} hours")
        if minutes > 0:
            time_parts.append(f"{minutes} minutes")
        if seconds > 0 or not time_parts:
            time_parts.append(f"{seconds} seconds")
        time_since = ", ".join(time_parts)
        logger.info(f"Time since last interaction: {time_since}")
        return time_since
    else:
        logger.warning("No timestamp found in last entry")
        return None


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
