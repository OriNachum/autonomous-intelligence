#!/bin/bash
# Gemma Setup Script

set -e

echo "=== Gemma Multimodal AI Assistant Setup ==="

# Check if running on Jetson
is_jetson() {
    if [ -f /etc/nv_tegra_release ] || [ -d /proc/device-tree/nvidia,tegra250-p2888 ]; then
        return 0
    else
        return 1
    fi
}

# Function to setup directories
setup_directories() {
    echo "Creating necessary directories..."
    mkdir -p models data logs notebooks
    chmod 755 models data logs notebooks
    echo "✓ Directories created"
}

# Function to download models
download_models() {
    echo "Downloading AI models..."
    
    # YOLOv6 model
    if [ ! -f models/yolov6n.pt ]; then
        echo "Downloading YOLOv6 model..."
        wget -O models/yolov6n.pt \
            https://github.com/meituan/YOLOv6/releases/download/0.4.0/yolov6n.pt
        echo "✓ YOLOv6 model downloaded"
    else
        echo "✓ YOLOv6 model already exists"
    fi
}

# Function to setup audio permissions
setup_audio() {
    echo "Setting up audio permissions..."
    
    # Add user to audio group
    sudo usermod -a -G audio $USER
    
    # Setup PulseAudio
    if ! pgrep -x "pulseaudio" > /dev/null; then
        pulseaudio --start
    fi
    
    echo "✓ Audio setup complete"
}

# Function to setup camera permissions
setup_camera() {
    echo "Setting up camera permissions..."
    
    # Add user to video group
    sudo usermod -a -G video $USER
    
    # Set camera permissions
    if [ -c /dev/video0 ]; then
        sudo chmod 666 /dev/video0
        echo "✓ Camera permissions set"
    else
        echo "⚠ Camera device /dev/video0 not found"
    fi
    
    if is_jetson; then
        # Jetson-specific camera setup
        if [ -c /dev/tegra-cam ]; then
            sudo chmod 666 /dev/tegra-cam
            echo "✓ Jetson camera permissions set"
        fi
    fi
}

# Function to install system dependencies
install_system_deps() {
    echo "Installing system dependencies..."
    
    # Update package list
    sudo apt-get update
    
    # Install common dependencies
    sudo apt-get install -y \
        python3-pip \
        python3-dev \
        build-essential \
        cmake \
        git \
        pkg-config \
        libgstreamer1.0-dev \
        libgstreamer-plugins-base1.0-dev \
        libgstreamer-plugins-bad1.0-dev \
        gstreamer1.0-plugins-base \
        gstreamer1.0-plugins-good \
        gstreamer1.0-plugins-bad \
        gstreamer1.0-plugins-ugly \
        gstreamer1.0-libav \
        gstreamer1.0-tools \
        portaudio19-dev \
        alsa-utils \
        pulseaudio \
        espeak \
        espeak-data \
        libespeak-dev \
        v4l-utils \
        curl \
        wget
    
    if is_jetson; then
        echo "Installing Jetson-specific dependencies..."
        sudo apt-get install -y \
            nvidia-l4t-gstreamer \
            nvidia-l4t-multimedia \
            nvidia-l4t-multimedia-utils
    fi
    
    echo "✓ System dependencies installed"
}

# Function to install Python dependencies
install_python_deps() {
    echo "Installing Python dependencies..."
    
    # Upgrade pip
    pip3 install --upgrade pip setuptools wheel
    
    # Install requirements
    pip3 install -r requirements.txt
    
    if is_jetson; then
        echo "Installing Jetson-specific Python packages..."
        pip3 install jetson-stats
    fi
    
    echo "✓ Python dependencies installed"
}

# Function to setup databases
setup_databases() {
    echo "Setting up databases..."
    
    # Check if Docker is available
    if command -v docker &> /dev/null; then
        echo "Docker found. Setting up databases with Docker..."
        
        if is_jetson; then
            echo "Using Jetson-optimized configuration..."
            docker-compose -f docker-compose.jetson.yml up -d milvus-lite neo4j-lite
        else
            echo "Using standard configuration..."
            docker-compose up -d milvus neo4j etcd minio
        fi
        
        echo "✓ Databases started with Docker"
    else
        echo "⚠ Docker not found. You'll need to set up Milvus and Neo4j manually."
        echo "  - Milvus: https://milvus.io/docs/install_standalone-docker.md"
        echo "  - Neo4j: https://neo4j.com/docs/operations-manual/current/installation/"
    fi
}

# Function to run tests
run_tests() {
    echo "Running basic tests..."
    
    # Test camera
    if [ -c /dev/video0 ]; then
        echo "Testing camera..."
        timeout 5s ffmpeg -f v4l2 -i /dev/video0 -vframes 1 -f null - 2>/dev/null && \
            echo "✓ Camera test passed" || echo "⚠ Camera test failed"
    fi
    
    # Test audio
    echo "Testing audio..."
    timeout 5s arecord -d 1 -f cd /tmp/test_audio.wav 2>/dev/null && \
        echo "✓ Audio recording test passed" || echo "⚠ Audio recording test failed"
    
    rm -f /tmp/test_audio.wav
    
    # Test TTS
    echo "Testing text-to-speech..."
    echo "Testing Gemma setup" | espeak 2>/dev/null && \
        echo "✓ TTS test passed" || echo "⚠ TTS test failed"
}

# Main setup function
main() {
    echo "Detected system: $(uname -m)"
    if is_jetson; then
        echo "Jetson device detected"
    fi
    
    # Run setup steps
    setup_directories
    
    if [ "$1" != "--skip-system" ]; then
        install_system_deps
    fi
    
    if [ "$1" != "--skip-python" ]; then
        install_python_deps
    fi
    
    download_models
    setup_audio
    setup_camera
    
    if [ "$1" != "--skip-databases" ]; then
        setup_databases
    fi
    
    if [ "$1" != "--skip-tests" ]; then
        run_tests
    fi
    
    echo ""
    echo "=== Setup Complete! ==="
    echo ""
    echo "To start Gemma:"
    echo "  ./run_gemma.py"
    echo ""
    echo "To start with Docker:"
    if is_jetson; then
        echo "  docker-compose -f docker-compose.jetson.yml up"
    else
        echo "  docker-compose up"
    fi
    echo ""
    echo "For help:"
    echo "  ./run_gemma.py --help"
    echo ""
    
    if groups $USER | grep -q '\baudio\b' && groups $USER | grep -q '\bvideo\b'; then
        echo "✓ User has necessary permissions"
    else
        echo "⚠ You may need to log out and back in for group permissions to take effect"
    fi
}

# Parse arguments
case "${1:-}" in
    --help|-h)
        echo "Gemma Setup Script"
        echo ""
        echo "Usage: $0 [OPTIONS]"
        echo ""
        echo "Options:"
        echo "  --skip-system    Skip system dependency installation"
        echo "  --skip-python    Skip Python dependency installation"
        echo "  --skip-databases Skip database setup"
        echo "  --skip-tests     Skip hardware tests"
        echo "  --help, -h       Show this help message"
        exit 0
        ;;
    *)
        main "$1"
        ;;
esac