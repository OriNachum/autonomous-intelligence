import sys
import os

if __name__ == "__main__":
    parent_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    if parent_dir not in sys.path:
        sys.path.append(parent_dir)
        
from persistency.local_file import load_history



history = load_history()
#main_system_prompt = load_prompt("main")

def main():
    print("Conversation History:\n")
    print(history)

if __name__ == "__main__":
    main()
