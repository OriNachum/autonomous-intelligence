#!/bin/bash

# Script to access and interact with the Codex container

CONTAINER_NAME="codex-assistant-codex-1"
ADAPTER_PORT="${API_ADAPTER_PORT:-8080}"

function show_help {
  echo "Usage: $0 [command]"
  echo ""
  echo "Commands:"
  echo "  --help, -h              Show this help"
  echo "  --shell, -s             Connect to container with bash (default)"
  echo "  --adapter-log, -l       Show API adapter log"
  echo "  --restart-adapter, -r   Restart the API adapter"
  echo "  --test-adapter, -t      Test the API adapter endpoints"
  echo "  --codex [args]          Run codex with the given arguments"
  echo "  [command]               Run arbitrary command in container"
  echo ""
  echo "Examples:"
  echo "  $0                      # Connect to container with bash"
  echo "  $0 --test-adapter       # Test the API adapter"
  echo "  $0 --codex --help       # Show codex help"
  echo "  $0 --codex \"Write a function to calculate fibonacci\""
}

# Check if container is running
function ensure_container_running {
  if ! docker ps | grep -q "${CONTAINER_NAME}"; then
    echo "Container ${CONTAINER_NAME} is not running."
    echo "Starting containers with docker-compose..."
    docker-compose -f docker-compose-codex.yaml up -d
    
    # Wait a bit for container to be ready
    echo "Waiting for container to be ready..."
    sleep 5
  fi
}

# Parse arguments
case "$1" in
  --help|-h)
    show_help
    exit 0
    ;;
  --shell|-s)
    ensure_container_running
    echo "Connecting to ${CONTAINER_NAME}..."
    docker exec -it ${CONTAINER_NAME} bash
    ;;
  --adapter-log|-l)
    ensure_container_running
    echo "Showing API adapter log..."
    docker exec -it ${CONTAINER_NAME} cat /app/api-adapter/server.log
    ;;
  --restart-adapter|-r)
    ensure_container_running
    echo "Restarting API adapter..."
    docker exec ${CONTAINER_NAME} bash -c "pkill -f 'python3 /app/api-adapter/server.py' || true"
    docker exec -d ${CONTAINER_NAME} bash -c "python3 /app/api-adapter/server.py > /app/api-adapter/server.log 2>&1 &"
    echo "API adapter restarted. Check logs with: $0 --adapter-log"
    ;;
  --test-adapter|-t)
    ensure_container_running
    echo "Testing API adapter..."
    docker exec -it ${CONTAINER_NAME} bash -c "cd /app/api-adapter && bash test-adapter.sh"
    ;;
  --codex)
    shift
    ensure_container_running
    echo "Running codex command: $@"
    docker exec -it ${CONTAINER_NAME} bash -c "export OPENAI_BASE_URL=http://localhost:${ADAPTER_PORT}/v1 && export OPENAI_API_KEY=dummy-key && codex $*"
    ;;
  "")
    ensure_container_running
    echo "Connecting to ${CONTAINER_NAME}..."
    docker exec -it ${CONTAINER_NAME} bash
    ;;
  *)
    ensure_container_running
    echo "Running command in ${CONTAINER_NAME}: $@"
    docker exec -it ${CONTAINER_NAME} bash -c "$*"
    ;;
esac
