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

echo " Downloading voice for piper-tts"
wget https://huggingface.co/rhasspy/piper-voices/resolve/v1.0.0/en/en_US/lessac/high/en_US-lessac-high.onnx
wget https://huggingface.co/rhasspy/piper-voices/resolve/v1.0.0/en/en_US/lessac/high/en_US-lessac-high.onnx.json

echo "Downloading kokoro models"
wget "https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files/kokoro-v0_19.onnx"
wget "https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files/voices.json"

pip install --upgrade pip
pip install -r requirements.txt

echo "Virtual environment initialized and dependencies installed."
echo "Make sure you have Ollama installed"
echo  "curl -fsSL https://ollama.com/install.sh | sh"
echo "source .venv/bin/activate"
