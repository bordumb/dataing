#!/bin/bash
# Quickstart E2E Test Script
# Tests the Docker Compose quickstart path end-to-end
#
# Prerequisites:
#   - Docker + Docker Compose v2
#   - ANTHROPIC_API_KEY environment variable set
#
# Usage:
#   ANTHROPIC_API_KEY=sk-ant-... bash docs/test-quickstart.sh
#
set -e

echo "=== Dataing Quickstart E2E Test ==="
echo ""

# Check prerequisites
if [ -z "$ANTHROPIC_API_KEY" ]; then
  echo "ERROR: ANTHROPIC_API_KEY environment variable is not set"
  echo "Usage: ANTHROPIC_API_KEY=sk-ant-... bash docs/test-quickstart.sh"
  exit 1
fi

if ! command -v docker &> /dev/null; then
  echo "ERROR: docker is not installed"
  exit 1
fi

if ! docker compose version &> /dev/null; then
  echo "ERROR: docker compose v2 is not available"
  exit 1
fi

# Cleanup function (called by trap on exit)
# shellcheck disable=SC2317
cleanup() {
  echo ""
  echo "=== Cleanup ==="
  docker compose down -v 2>/dev/null || true
}
trap cleanup EXIT

# Start timer
START_TIME=$(date +%s)

# Setup
echo "=== Step 1: Setup ==="
if [ ! -f .env ]; then
  cp .env.example .env
fi

# Ensure API key is in .env (append if not present)
if ! grep -q "ANTHROPIC_API_KEY=" .env 2>/dev/null; then
  echo "ANTHROPIC_API_KEY=${ANTHROPIC_API_KEY}" >> .env
fi

# Generate encryption key if not present
if ! grep -q "DATADR_ENCRYPTION_KEY=" .env 2>/dev/null; then
  KEY=$(python3 -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())")
  echo "DATADR_ENCRYPTION_KEY=${KEY}" >> .env
fi

echo "Environment configured"

# Start stack
echo ""
echo "=== Step 2: Start Stack ==="
docker compose up -d
echo "Stack started"

# Wait for health
echo ""
echo "=== Step 3: Wait for Health ==="
echo "Waiting for API to be healthy (timeout: 120s)..."
WAIT_START=$(date +%s)
until curl -sf http://localhost:8000/health > /dev/null 2>&1; do
  ELAPSED=$(($(date +%s) - WAIT_START))
  if [ $ELAPSED -gt 120 ]; then
    echo "FAIL: API did not become healthy within 120 seconds"
    docker compose logs api
    exit 1
  fi
  echo "  Waiting... (${ELAPSED}s)"
  sleep 5
done
echo "API is healthy!"

# Verify demo datasource
echo ""
echo "=== Step 4: Verify Demo Datasource ==="
DATASOURCES=$(curl -s -H "X-API-Key: dd_demo_12345" http://localhost:8000/api/v1/datasources)
echo "Datasources response: $DATASOURCES"

# Trigger investigation
echo ""
echo "=== Step 5: Trigger Investigation ==="
RESPONSE=$(curl -s -X POST http://localhost:8000/api/v1/investigations \
  -H "Content-Type: application/json" \
  -H "X-API-Key: dd_demo_12345" \
  -d '{
    "alert": {
      "table": "orders",
      "column": "user_id",
      "metric": "null_rate",
      "anomaly_type": "spike",
      "description": "NULL rate increased from 1% to 15%"
    }
  }')

echo "Response: $RESPONSE"

# Extract investigation ID
INV_ID=$(echo "$RESPONSE" | python3 -c "import sys,json; print(json.load(sys.stdin).get('investigation_id', ''))" 2>/dev/null || echo "")

if [ -z "$INV_ID" ]; then
  echo "FAIL: Could not extract investigation_id from response"
  exit 1
fi

echo "Investigation ID: $INV_ID"

# Poll for completion
echo ""
echo "=== Step 6: Wait for Investigation ==="
STATUS="unknown"
for i in $(seq 1 60); do
  RESULT=$(curl -s "http://localhost:8000/api/v1/investigations/$INV_ID" \
    -H "X-API-Key: dd_demo_12345")
  STATUS=$(echo "$RESULT" | python3 -c "import sys,json; print(json.load(sys.stdin).get('status','unknown'))" 2>/dev/null || echo "unknown")
  PHASE=$(echo "$RESULT" | python3 -c "import sys,json; print(json.load(sys.stdin).get('phase',''))" 2>/dev/null || echo "")
  echo "  Status: $STATUS (phase: $PHASE) [$i/60]"

  if [ "$STATUS" = "completed" ]; then
    break
  elif [ "$STATUS" = "failed" ]; then
    echo "FAIL: Investigation failed"
    echo "$RESULT" | python3 -m json.tool
    exit 1
  fi

  sleep 5
done

# Report results
END_TIME=$(date +%s)
DURATION=$((END_TIME - START_TIME))

echo ""
echo "=== Results ==="
echo "Investigation status: $STATUS"
echo "Total duration: ${DURATION}s"

if [ "$STATUS" = "completed" ]; then
  echo ""
  echo "=== Investigation Summary ==="
  curl -s "http://localhost:8000/api/v1/investigations/$INV_ID" \
    -H "X-API-Key: dd_demo_12345" | python3 -m json.tool
  echo ""
  echo "PASS: Quickstart E2E test completed successfully!"
  exit 0
else
  echo "FAIL: Investigation did not complete within timeout"
  exit 1
fi
