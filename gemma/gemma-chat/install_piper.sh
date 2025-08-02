#!/bin/bash
# Install Piper TTS on ARM64 (Jetson) systems

echo "Installing Piper TTS for ARM64..."

# Check if wheel exists
WHEEL_PATH="$HOME/git/jetson-pypi/pypi-mirror-wget/pypi.jetson-ai-lab.io/jp6/cu129/piper-1.3.0-cp312-cp312-linux_aarch64.whl"

if [ -f "$WHEEL_PATH" ]; then
    echo "Found Piper wheel at: $WHEEL_PATH"
    echo "Installing from wheel..."
    pip install "$WHEEL_PATH"
else
    echo "Wheel not found at expected location. Downloading binary instead..."
    
    # Create directory for piper
    mkdir -p ~/piper-install
    cd ~/piper-install

    # Download the ARM64 version of Piper
    echo "Downloading Piper ARM64 binary..."
    wget https://github.com/rhasspy/piper/releases/download/v1.2.0/piper_arm64.tar.gz

    # Extract
    echo "Extracting..."
    tar -xzf piper_arm64.tar.gz

    # Install to /usr/local/bin (requires sudo)
    echo "Installing piper to /usr/local/bin..."
    sudo cp piper /usr/local/bin/
    sudo chmod +x /usr/local/bin/piper
    
    # Clean up
    cd ~
    rm -rf ~/piper-install
fi

# Create voices directory
echo "Creating voices directory..."
mkdir -p ~/piper-voices
cd ~/piper-voices

# Download a voice model
echo "Downloading English voice model..."
wget https://huggingface.co/rhasspy/piper-voices/resolve/main/en/en_US/amy/medium/en_US-amy-medium.onnx
wget https://huggingface.co/rhasspy/piper-voices/resolve/main/en/en_US/amy/medium/en_US-amy-medium.onnx.json

# Test installation
echo "Testing Piper installation..."
echo "Hello, Piper is now installed!" | piper --model ~/piper-voices/en_US-amy-medium.onnx --output_file test.wav

if [ -f test.wav ]; then
    echo "Success! Piper is installed and working."
    echo "Test audio file created: test.wav"
    rm test.wav
else
    echo "Error: Piper test failed."
fi

# Clean up
cd ~
rm -rf ~/piper-install

echo "Installation complete!"
echo "Voice model installed at: ~/piper-voices/en_US-amy-medium.onnx"