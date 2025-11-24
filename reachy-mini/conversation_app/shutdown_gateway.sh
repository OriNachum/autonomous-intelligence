#!/bin/bash
# Graceful shutdown script for Reachy Gateway

echo "🛑 Shutting down Reachy Gateway gracefully..."

# Shutdown gateway (which will also cleanup the daemon internally)
echo "📤 Stopping Gateway..."
GATEWAY_PID=$(pgrep -f "gateway.py" | grep -v shutdown)
if [ -n "$GATEWAY_PID" ]; then
    echo "📍 Found gateway process: PID $GATEWAY_PID"
    kill -TERM $GATEWAY_PID
    
    # Wait for gateway to stop (max 10 seconds)
    # The Python application will handle daemon cleanup internally
    for i in {1..10}; do
        if ! kill -0 $GATEWAY_PID 2>/dev/null; then
            echo "✅ Gateway stopped gracefully"
            break
        fi
        echo "⏳ Waiting for gateway to stop... ($i/10)"
        sleep 1
    done
    
    # Force kill if still running
    if kill -0 $GATEWAY_PID 2>/dev/null; then
        echo "⚠️  Gateway did not stop gracefully, forcing shutdown..."
        kill -KILL $GATEWAY_PID
        sleep 1
    fi
else
    echo "⚠️  Gateway process not found"
fi

echo "✅ Gateway shutdown complete"
exit 0
