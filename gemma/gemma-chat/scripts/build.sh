#!/bin/bash
# Gemma Build Script

set -e

echo "=== Gemma Build Script ==="

# Detect system type
is_jetson() {
    if [ -f /etc/nv_tegra_release ] || [ -d /proc/device-tree/nvidia,tegra250-p2888 ]; then
        return 0
    else
        return 1
    fi
}

# Build function
build_gemma() {
    local target="${1:-standard}"
    
    echo "Building Gemma for target: $target"
    
    case "$target" in
        "jetson")
            echo "Building for NVIDIA Jetson..."
            docker build -f Dockerfile.jetson -t gemma:jetson .
            echo "✓ Jetson build complete"
            ;;
        "standard")
            echo "Building standard Docker image..."
            docker build -f Dockerfile -t gemma:latest .
            echo "✓ Standard build complete"
            ;;
        "dev")
            echo "Building development image..."
            docker build -f Dockerfile -t gemma:dev --target dev .
            echo "✓ Development build complete"
            ;;
        *)
            echo "Unknown target: $target"
            echo "Available targets: standard, jetson, dev"
            exit 1
            ;;
    esac
}

# Auto-detect and build
auto_build() {
    if is_jetson; then
        echo "Jetson device detected, building Jetson image..."
        build_gemma "jetson"
    else
        echo "Standard system detected, building standard image..."
        build_gemma "standard"
    fi
}

# Deploy function
deploy_gemma() {
    local target="${1:-auto}"
    
    echo "Deploying Gemma..."
    
    # Stop existing containers
    echo "Stopping existing containers..."
    docker-compose down 2>/dev/null || true
    
    case "$target" in
        "jetson")
            echo "Deploying Jetson configuration..."
            docker-compose -f docker-compose.jetson.yml up -d
            ;;
        "standard")
            echo "Deploying standard configuration..."
            docker-compose up -d
            ;;
        "auto")
            if is_jetson; then
                echo "Auto-deploying Jetson configuration..."
                docker-compose -f docker-compose.jetson.yml up -d
            else
                echo "Auto-deploying standard configuration..."
                docker-compose up -d
            fi
            ;;
        *)
            echo "Unknown deployment target: $target"
            exit 1
            ;;
    esac
    
    echo "✓ Deployment complete"
    
    # Show status
    echo ""
    echo "Container status:"
    docker-compose ps
}

# Clean function
clean_gemma() {
    echo "Cleaning up Gemma containers and images..."
    
    # Stop and remove containers
    docker-compose down --volumes --remove-orphans 2>/dev/null || true
    docker-compose -f docker-compose.jetson.yml down --volumes --remove-orphans 2>/dev/null || true
    
    # Remove images
    docker rmi gemma:latest gemma:jetson gemma:dev 2>/dev/null || true
    
    # Clean up volumes (optional)
    if [ "$1" = "--volumes" ]; then
        echo "Removing volumes..."
        docker volume rm $(docker volume ls -q | grep gemma) 2>/dev/null || true
    fi
    
    echo "✓ Cleanup complete"
}

# Status function
show_status() {
    echo "=== Gemma Status ==="
    
    # Show running containers
    echo "Running containers:"
    docker-compose ps 2>/dev/null || echo "No containers running"
    
    echo ""
    
    # Show images
    echo "Built images:"
    docker images | grep gemma || echo "No gemma images found"
    
    echo ""
    
    # Show logs if container is running
    if docker-compose ps | grep -q "gemma"; then
        echo "Recent logs:"
        docker-compose logs --tail=10 gemma 2>/dev/null || true
    fi
}

# Test function
test_gemma() {
    echo "=== Testing Gemma ==="
    
    # Check if container is running
    if ! docker-compose ps | grep -q "gemma.*Up"; then
        echo "Gemma container is not running. Starting..."
        deploy_gemma "auto"
        sleep 10
    fi
    
    # Test event system
    echo "Testing event system..."
    docker-compose exec gemma python -c "
import socket
import time
try:
    s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    s.connect('/tmp/gemma_events.sock')
    s.close()
    print('✓ Event system test passed')
except Exception as e:
    print(f'⚠ Event system test failed: {e}')
" 2>/dev/null || echo "⚠ Event system test failed"
    
    # Test databases
    echo "Testing databases..."
    if docker-compose ps | grep -q "milvus.*Up"; then
        echo "✓ Milvus is running"
    else
        echo "⚠ Milvus is not running"
    fi
    
    if docker-compose ps | grep -q "neo4j.*Up"; then
        echo "✓ Neo4j is running"
    else
        echo "⚠ Neo4j is not running"
    fi
}

# Help function
show_help() {
    echo "Gemma Build Script"
    echo ""
    echo "Usage: $0 [COMMAND] [OPTIONS]"
    echo ""
    echo "Commands:"
    echo "  build [target]   Build Docker images (targets: standard, jetson, dev, auto)"
    echo "  deploy [target]  Deploy containers (targets: standard, jetson, auto)"
    echo "  clean [--volumes] Clean up containers and images"
    echo "  status           Show system status"
    echo "  test             Run basic tests"
    echo "  logs             Show container logs"
    echo "  help             Show this help message"
    echo ""
    echo "Examples:"
    echo "  $0 build auto    # Auto-detect and build appropriate image"
    echo "  $0 deploy jetson # Deploy Jetson configuration"
    echo "  $0 clean --volumes # Clean up everything including volumes"
    echo ""
}

# Parse arguments
case "${1:-help}" in
    build)
        build_gemma "${2:-auto}"
        ;;
    deploy)
        deploy_gemma "${2:-auto}"
        ;;
    clean)
        clean_gemma "$2"
        ;;
    status)
        show_status
        ;;
    test)
        test_gemma
        ;;
    logs)
        echo "=== Gemma Logs ==="
        docker-compose logs -f gemma
        ;;
    auto)
        auto_build
        deploy_gemma "auto"
        ;;
    help|--help|-h)
        show_help
        ;;
    *)
        echo "Unknown command: $1"
        echo "Use '$0 help' for usage information"
        exit 1
        ;;
esac