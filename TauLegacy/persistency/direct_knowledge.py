import os

DIRECT_KNOWLEDGE_FILE = "direct_knowledge.md"

def load_direct_knowledge():
    if os.path.exists(DIRECT_KNOWLEDGE_FILE):
        with open(DIRECT_KNOWLEDGE_FILE, "r") as file:
            return file.read()
    else:
        return ""
    
def add_to_direct_knowledge(new_knowledge):
    with open(DIRECT_KNOWLEDGE_FILE, "a") as file:
        file.write(new_knowledge)

def save_over_direct_knowledge(new_knowledge):
    with open(DIRECT_KNOWLEDGE_FILE, "w") as file:
        file.write(new_knowledge)
