#!/bin/bash
# Smoke test script for Dataing Docker Compose stack
# Verifies all services are healthy and responding

set -e

RED='\033[0;31m'
GREEN='\033[0;32m'
NC='\033[0m' # No Color

TIMEOUT=${TIMEOUT:-120}

echo "Dataing Smoke Test"
echo "=================="
echo ""

# Check if compose is running
if ! docker compose ps --quiet 2>/dev/null | head -1 > /dev/null; then
    echo -e "${RED}ERROR: Docker Compose stack is not running${NC}"
    echo "Run 'docker compose up -d' first"
    exit 1
fi

echo "Waiting for services to become healthy (timeout: ${TIMEOUT}s)..."
echo ""

# Helper function to wait for endpoint (cross-platform)
wait_for_endpoint() {
    local url=$1
    local max_attempts=$2
    local attempt=1
    while [ "$attempt" -le "$max_attempts" ]; do
        if curl -sf "$url" > /dev/null 2>&1; then
            return 0
        fi
        sleep 2
        attempt=$((attempt + 1))
    done
    return 1
}

# Wait for API
echo -n "API (http://localhost:8000/health): "
if wait_for_endpoint "http://localhost:8000/health" 60; then
    echo -e "${GREEN}OK${NC}"
else
    echo -e "${RED}FAILED${NC}"
    exit 1
fi

# Wait for Frontend
echo -n "Frontend (http://localhost:3000): "
if wait_for_endpoint "http://localhost:3000/" 15; then
    echo -e "${GREEN}OK${NC}"
else
    echo -e "${RED}FAILED${NC}"
    exit 1
fi

# Wait for Temporal UI
echo -n "Temporal UI (http://localhost:8233): "
if wait_for_endpoint "http://localhost:8233/" 15; then
    echo -e "${GREEN}OK${NC}"
else
    echo -e "${RED}FAILED${NC}"
    exit 1
fi

echo ""
echo "----------------------------------------"
echo -e "${GREEN}All smoke tests passed!${NC}"
echo ""

# Show service status
echo "Service Status:"
docker compose ps --format "table {{.Service}}\t{{.Status}}"
echo ""

# Show memory usage
echo "Memory Usage:"
docker stats --no-stream --format "table {{.Name}}\t{{.MemUsage}}\t{{.CPUPerc}}"
