#!/bin/bash

# Script to update and restart the API adapter

CONTAINER_NAME="${CONTAINER_NAME:-codex-assistant-codex-1}"

echo "Updating API adapter in container $CONTAINER_NAME..."

# Check if container is running
if ! docker ps | grep -q "$CONTAINER_NAME"; then
  echo "Error: Container $CONTAINER_NAME is not running."
  echo "Start the container first with: docker-compose -f docker-compose-codex.yaml up -d"
  exit 1
fi

# Copy updated files to the container
echo "Copying updated files to container..."
docker exec "$CONTAINER_NAME" bash -c "cd /app/api-adapter && pip install -r requirements.txt"

# Restart the adapter
echo "Restarting API adapter..."
docker exec "$CONTAINER_NAME" bash -c "pkill -f 'python3 /app/api-adapter/server.py' || true"
docker exec -d "$CONTAINER_NAME" bash -c "python3 /app/api-adapter/server.py > /app/api-adapter/server.log 2>&1 &"

echo "API adapter updated and restarted."
echo "Check logs with: docker exec $CONTAINER_NAME cat /app/api-adapter/server.log"
