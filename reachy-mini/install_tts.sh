#!/bin/bash
# Installation script for piper1-gpl TTS system

set -e

source .venv/bin/activate

echo "=================================="
echo "Installing piper1-gpl TTS System"
echo "=================================="

# Check if running on Linux
if [[ "$OSTYPE" != "linux-gnu"* ]]; then
    echo "⚠️  This script is designed for Linux systems"
    echo "   Please install piper1-gpl manually from:"
    echo "   https://github.com/OHF-Voice/piper1-gpl"
    exit 1
fi

# Check for required tools
echo ""
echo "Checking prerequisites..."

# Check for git
if ! command -v git &> /dev/null; then
    echo "❌ git is not installed"
    echo "   Install with: sudo apt-get install git"
    exit 1
fi
echo "✓ git found"

# Check for build tools
if ! command -v cmake &> /dev/null; then
    echo "⚠️  cmake not found - may be needed for building"
    echo "   Install with: sudo apt-get install cmake build-essential"
fi

# Check for aplay (ALSA)
if ! command -v aplay &> /dev/null; then
    echo "⚠️  aplay (ALSA) not found"
    echo "   Install with: sudo apt-get install alsa-utils"
    read -p "   Continue anyway? (y/n) " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        exit 1
    fi
else
    echo "✓ aplay found"
fi

# Ask where to install
echo ""
echo "Installation options:"
echo "1. Clone piper1-gpl to current directory and build from source"
echo "2. Download pre-built binary (if available)"
echo "3. Skip installation (I'll install manually)"
read -p "Select option (1-3): " choice

case $choice in
    1)
        echo ""
        echo "Cloning piper1-gpl repository..."
        if [ -d "piper1-gpl" ]; then
            echo "⚠️  Directory 'piper1-gpl' already exists"
            read -p "   Remove and re-clone? (y/n) " -n 1 -r
            echo
            if [[ $REPLY =~ ^[Yy]$ ]]; then
                rm -rf piper1-gpl
            else
                echo "Skipping clone..."
            fi
        fi
        
        if [ ! -d "piper1-gpl" ]; then
            git clone https://github.com/OHF-Voice/piper1-gpl.git
        fi
        
        cd piper1-gpl
        
        echo ""
        echo "📋 Please follow the build instructions in the repository:"
        echo "   - Check README.md for build requirements"
        echo "   - Run the build commands"
        echo "   - Add the piper1 executable to your PATH"
        echo ""
        echo "Once built, you can:"
        echo "1. Add to PATH: export PATH=\"\$PATH:$(pwd)/build\""
        echo "2. Or create symlink: sudo ln -s $(pwd)/build/piper1 /usr/local/bin/piper1"
        ;;
        
    2)
        echo ""
        echo "Checking for pre-built binaries..."
        echo "Please visit: https://github.com/OHF-Voice/piper1-gpl/releases"
        echo "Download the appropriate binary for your system and add to PATH"
        ;;
        
    3)
        echo ""
        echo "Skipping automatic installation"
        echo "Please install piper1-gpl manually from:"
        echo "https://github.com/OHF-Voice/piper1-gpl"
        ;;
        
    *)
        echo "Invalid option"
        exit 1
        ;;
esac

echo ""
echo "=================================="
echo "Installation Notes"
echo "=================================="
echo ""
echo "After installing piper1, verify it works:"
echo "  piper1 --version"
echo ""
echo "Test TTS queue:"
echo "  python tts_queue.py"
echo ""
echo "Then run the chat application:"
echo "  python chat_app.py"
echo ""
echo "For more information, see TTS_FEATURE.md"
echo ""
