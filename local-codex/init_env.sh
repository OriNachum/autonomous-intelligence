#!/bin/bash

wget_if_not_exists() {
    local url="$1"
    local filename="$2"
    
    # If filename is not provided, extract it from the URL
    if [ -z "$filename" ]; then
        filename=$(basename "$url")
    fi
    
    if [ ! -f "$filename" ]; then
        echo "File $filename does not exist. Downloading..."
        wget "$url" -O "$filename"
        
        # Check if download was successful
        if [ $? -eq 0 ]; then
            echo "Successfully downloaded $filename"
            return 0
        else
            echo "Failed to download $filename"
            return 1
        fi
    else
        echo "File $filename already exists. Skipping download."
        return 0
    fi
}


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
wget_if_not_exists https://huggingface.co/rhasspy/piper-voices/resolve/v1.0.0/en/en_US/lessac/high/en_US-lessac-high.onnx
wget_if_not_exists https://huggingface.co/rhasspy/piper-voices/resolve/v1.0.0/en/en_US/lessac/high/en_US-lessac-high.onnx.json

echo "Downloading kokoro models"
wget_if_not_exists https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files/kokoro-v0_19.onnx
wget_if_not_exists https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files/voices.json
wget_if_not_exists https://huggingface.co/hexgrad/Kokoro-82M/resolve/main/kokoro-v0_19.pth


pip install --upgrade pip
pip install -r requirements.txt

echo "Virtual environment initialized and dependencies installed."
echo "Make sure you have Ollama installed"
echo  "curl -fsSL https://ollama.com/install.sh | sh"
echo "source .venv/bin/activate"
