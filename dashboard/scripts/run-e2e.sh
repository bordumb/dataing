#!/bin/bash
# E2E Test Runner Script
# Ensures the demo environment is running before executing Playwright tests

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DASHBOARD_DIR="$(dirname "$SCRIPT_DIR")"
DEMO_DIR="$(dirname "$DASHBOARD_DIR")/demo"

echo "=== DataDr E2E Test Runner ==="

# Check if demo directory exists
if [ ! -d "$DEMO_DIR" ]; then
    echo "Error: Demo directory not found at $DEMO_DIR"
    exit 1
fi

# Function to check if services are healthy
check_services() {
    echo "Checking service health..."

    # Check API health
    if curl -s --max-time 5 http://localhost:8000/docs > /dev/null 2>&1; then
        echo "  ✓ API is responding"
        return 0
    else
        echo "  ✗ API is not responding"
        return 1
    fi
}

# Function to wait for services
wait_for_services() {
    local max_attempts=30
    local attempt=1

    echo "Waiting for services to be ready..."

    while [ $attempt -le $max_attempts ]; do
        if check_services; then
            echo "Services are ready!"
            return 0
        fi

        echo "  Attempt $attempt/$max_attempts - waiting 5s..."
        sleep 5
        attempt=$((attempt + 1))
    done

    echo "Error: Services did not become ready in time"
    return 1
}

# Start services if not running
start_services() {
    echo "Starting demo services..."
    cd "$DEMO_DIR"

    # Check if containers are already running
    if docker compose ps --status running | grep -q "api"; then
        echo "  Services already running, checking health..."

        # Check if API is healthy
        local api_status
        api_status=$(docker compose ps api --format json 2>/dev/null | grep -o '"Health":"[^"]*"' | cut -d'"' -f4)

        if [ "$api_status" = "unhealthy" ]; then
            echo "  API is unhealthy, restarting..."
            docker compose restart api
        fi
    else
        echo "  Starting containers..."
        docker compose up -d
    fi

    cd "$DASHBOARD_DIR"
}

# Main execution
main() {
    # Parse arguments
    local skip_services=false
    local test_args=""

    while [[ $# -gt 0 ]]; do
        case $1 in
            --skip-services)
                skip_services=true
                shift
                ;;
            *)
                test_args="$test_args $1"
                shift
                ;;
        esac
    done

    # Start services unless skipped
    if [ "$skip_services" = false ]; then
        start_services
        wait_for_services
    fi

    # Run Playwright tests
    echo ""
    echo "=== Running Playwright Tests ==="
    cd "$DASHBOARD_DIR"

    # Set the test base URL to the Docker dashboard
    export TEST_BASE_URL="http://localhost:3000"

    # Run tests with any additional arguments
    if [ -n "$test_args" ]; then
        pnpm exec playwright test "$test_args"
    else
        pnpm exec playwright test
    fi
}

main "$@"
