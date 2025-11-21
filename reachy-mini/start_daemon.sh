#!/bin/bash
# Startup wrapper for Reachy Mini Daemon with signal handling

# Function to handle shutdown signals
shutdown_handler() {
    echo ""
    echo "🛑 Received shutdown signal (Ctrl+C)..."
    /app/shutdown_daemon.sh
    exit 0
}

# Trap SIGTERM and SIGINT signals
trap shutdown_handler SIGTERM SIGINT

# Install dependencies
echo "📦 Installing dependencies..."
apt-get update -qq
apt-get install -y -qq portaudio*-dev libgl1 libusb-1.0-0 git 
pip install --no-cache-dir -q -r /app/requirements.txt

# Start the daemon
echo "🤖 Starting Reachy Mini Daemon..."
echo "💡 Press Ctrl+C to shutdown gracefully"
reachy-mini-daemon &

# Store the daemon PID
DAEMON_PID=$!

# Wait for daemon to start up
echo "⏳ Waiting for daemon to initialize..."
sleep 5


# Apply ReSpeaker reboot fix after daemon started
echo "🎤 Applying ReSpeaker reboot fix..."
if [ ! -d "/tmp/respeaker" ]; then
    echo "🎤 Cloning ReSpeaker repository..."
    git clone --depth 1 https://github.com/respeaker/reSpeaker_XVF3800_USB_4MIC_ARRAY /tmp/respeaker
fi

if [ -f "/tmp/respeaker/host_control/jetson/xvf_host" ]; then
    cd /tmp/respeaker/host_control/jetson/
    chmod +x xvf_host
    ./xvf_host REBOOT 1
    echo "✓ ReSpeaker reboot completed"
    sleep 2
    cd /app
else
    echo "⚠️  ReSpeaker xvf_host tool not found, skipping reboot"
fi

# Wait for the daemon process
wait $DAEMON_PID
