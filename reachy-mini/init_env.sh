#!/bin/bash

# Define the name of the virtual environment
ENV_NAME=".venv"

# Check if the virtual environment directory exists
if [ ! -d "$ENV_NAME" ]; then
    # Create the virtual environment
    python3 -m venv "$ENV_NAME"
fi

# Activate the virtual environment
source "$ENV_NAME/bin/activate"

# Install dependencies from requirements.txt
pip install -r requirements.txt

echo -e "\033[0;32mEnvironment setup complete.\033[0m"

