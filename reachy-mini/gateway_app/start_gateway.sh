#!/bin/bash
# Startup wrapper for Reachy Gateway with signal handling

# Function to handle shutdown signals
shutdown_handler() {
    echo ""
    echo "🛑 Received shutdown signal (Ctrl+C)..."
    /app/gateway_app/shutdown_gateway.sh
    exit 0
}

# Trap SIGTERM and SIGINT signals
trap shutdown_handler SIGTERM SIGINT

# Install dependencies
echo "📦 Installing dependencies..."
apt-get update -qq
apt-get install -y -qq portaudio*-dev libgl1 libusb-1.0-0 git alsa-utils
pip install --no-cache-dir -q -r /app/gateway_app/requirements.txt

# Start the gateway (daemon will be spawned internally by Python)
echo "🚀 Starting Reachy Gateway..."
echo "💡 The daemon will be spawned automatically by the gateway application"
echo "💡 Press Ctrl+C to shutdown gracefully"

# Change to gateway_app directory to access its modules
cd /app/gateway_app

# Run the gateway (this will block and spawn daemon internally)
python3 gateway.py --device "${AUDIO_DEVICE_NAME:-Reachy}" --language "${LANGUAGE:-en}"

# If gateway exits, trigger shutdown
echo "🚀 Gateway stopped, shutting down..."
shutdown_handler
