#!/bin/bash

# Create the virtual environment if it doesn't exist
if [ ! -d ".venv" ]; then
    echo "Creating virtual environment..."
    python3 -m venv .venv
fi

# Activate the virtual environment
source .venv/bin/activate

# Install required packages
echo "Installing dependencies..."
sudo apt-get update
sudo apt-get install nmap portaudio19-dev python3-pyaudio espeak
pip3 install --upgrade pip
pip3 install -r requirements.txt

echo "Virtual environment initialized and dependencies installed."
echo "source .venv/bin/activate"
