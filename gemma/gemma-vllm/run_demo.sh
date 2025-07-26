#!/bin/bash

# Gemma 3n vLLM Demo Runner
# Simple wrapper to run the demo CLI with docker-compose

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

print_usage() {
    echo "Usage: $0 [OPTIONS]"
    echo ""
    echo "Options:"
    echo "  --text, -t TEXT        Text input"
    echo "  --image, -i PATH       Image file path (can be used multiple times)"
    echo "  --audio, -a PATH       Audio file path"
    echo "  --verbose, -v          Verbose output"
    echo "  --help, -h             Show this help"
    echo ""
    echo "Examples:"
    echo "  $0 --text 'Hello, how are you?'"
    echo "  $0 --text 'What do you see?' --image ./examples/photo.jpg"
    echo "  $0 --text 'Analyze this' --image img1.jpg --image img2.jpg"
    echo "  $0 --text 'Transcribe this' --audio recording.wav"
}

check_dependencies() {
    if ! command -v docker &> /dev/null; then
        echo -e "${RED}Error: Docker is not installed${NC}"
        exit 1
    fi
    
    if ! command -v docker-compose &> /dev/null && ! docker compose version &> /dev/null; then
        echo -e "${RED}Error: Docker Compose is not installed${NC}"
        exit 1
    fi
}

check_vllm_service() {
    echo -e "${YELLOW}Checking if vLLM service is running...${NC}"
    
    # Check if vLLM container is running
    if ! docker-compose ps vllm | grep -q "Up"; then
        echo -e "${YELLOW}vLLM service is not running. Starting it now...${NC}"
        echo "This may take several minutes to download and start the model."
        docker-compose up -d vllm
        
        # Wait for health check
        echo "Waiting for vLLM service to be ready..."
        timeout=300  # 5 minutes
        elapsed=0
        while [ $elapsed -lt $timeout ]; do
            if docker-compose ps vllm | grep -q "healthy"; then
                echo -e "${GREEN}vLLM service is ready!${NC}"
                break
            fi
            sleep 5
            elapsed=$((elapsed + 5))
            echo "Waiting... ($elapsed/${timeout}s)"
        done
        
        if [ $elapsed -ge $timeout ]; then
            echo -e "${RED}Error: vLLM service failed to start within timeout${NC}"
            docker-compose logs vllm
            exit 1
        fi
    else
        echo -e "${GREEN}vLLM service is already running${NC}"
    fi
}

# Change to script directory
cd "$SCRIPT_DIR"

# Check for help
if [[ "$1" == "--help" || "$1" == "-h" ]]; then
    print_usage
    exit 0
fi

# Check dependencies
check_dependencies

# Check if .env file exists
if [[ ! -f .env ]]; then
    echo -e "${YELLOW}Warning: .env file not found. Creating from template...${NC}"
    cp .env.sample .env
    echo -e "${YELLOW}Please edit .env file and add your HF_TOKEN${NC}"
fi

# Check vLLM service
check_vllm_service

# Run the demo CLI
echo -e "${GREEN}Running Gemma 3n demo...${NC}"
docker-compose run --rm demo-cli python demo_cli.py "$@"