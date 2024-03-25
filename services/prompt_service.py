import os

def load_prompt(name):
    system_prompt = _load_role_prompt(name, "system")
    user_prompt = _load_role_prompt(name, "user")
    return system_prompt, user_prompt

def _load_role_prompt(name, role):
    role_prompt_file = f"./prompts/{name}/{name}.{role}.md"
    if os.path.exists(role_prompt_file):
        with open(role_prompt_file, "r") as file:
            return file.read()
    else:
        return ""
    
