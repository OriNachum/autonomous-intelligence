#!/bin/bash
# Graceful shutdown script for Reachy Mini Daemon

echo "🛑 Shutting down Reachy Mini Daemon gracefully..."

# Get the PID of the reachy-mini-daemon process
DAEMON_PID=$(pgrep -f "reachy-mini-daemon")

if [ -z "$DAEMON_PID" ]; then
    echo "⚠️  Reachy daemon process not found"
    exit 0
fi

echo "📍 Found daemon process: PID $DAEMON_PID"

# Send SIGTERM to allow graceful shutdown
echo "📤 Sending SIGTERM to daemon..."
kill -TERM $DAEMON_PID

# Wait for the process to terminate gracefully (max 10 seconds)
for i in {1..10}; do
    if ! kill -0 $DAEMON_PID 2>/dev/null; then
        echo "✅ Daemon stopped gracefully"
        exit 0
    fi
    echo "⏳ Waiting for daemon to stop... ($i/10)"
    sleep 1
done

# If still running after 10 seconds, force kill
if kill -0 $DAEMON_PID 2>/dev/null; then
    echo "⚠️  Daemon did not stop gracefully, forcing shutdown..."
    kill -KILL $DAEMON_PID
    sleep 1
fi

echo "✅ Daemon shutdown complete"
exit 0
