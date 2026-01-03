#!/bin/bash
# DataDr Demo Acceptance Test
# Run this script to verify the demo is working correctly

set -e

echo "=== DataDr Demo Acceptance Test ==="
echo ""

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Test counters
PASSED=0
FAILED=0

pass() {
    echo -e "${GREEN}[PASS]${NC} $1"
    ((PASSED++))
}

fail() {
    echo -e "${RED}[FAIL]${NC} $1"
    ((FAILED++))
}

# shellcheck disable=SC2317  # Function may be used in future tests
warn() {
    echo -e "${YELLOW}[WARN]${NC} $1"
}

# =============================================================================
# Test 1: Verify fixtures exist
# =============================================================================
echo "[1/7] Checking demo fixtures..."

if [ -d "demo/fixtures/null_spike" ]; then
    pass "null_spike fixture directory exists"
else
    fail "null_spike fixture directory missing"
fi

if [ -f "demo/fixtures/null_spike/orders.parquet" ]; then
    pass "orders.parquet exists"
else
    fail "orders.parquet missing - run 'cd demo && uv run python generate.py'"
fi

if [ -f "demo/fixtures/null_spike/manifest.json" ]; then
    pass "manifest.json exists"
else
    fail "manifest.json missing"
fi

# =============================================================================
# Test 2: Verify all fixture scenarios exist
# =============================================================================
echo ""
echo "[2/7] Checking all fixture scenarios..."

SCENARIOS=("baseline" "null_spike" "volume_drop" "schema_drift" "duplicates" "late_arriving" "orphaned_records")

for scenario in "${SCENARIOS[@]}"; do
    if [ -d "demo/fixtures/$scenario" ]; then
        pass "$scenario fixture exists"
    else
        fail "$scenario fixture missing"
    fi
done

# =============================================================================
# Test 3: Verify fixture has anomaly (using DuckDB)
# =============================================================================
echo ""
echo "[3/7] Verifying NULL spike anomaly in fixtures..."

ANOMALY_CHECK=$(uv run python -c "
import duckdb
conn = duckdb.connect()
result = conn.execute('''
SELECT
    DATE_TRUNC('day', created_at) AS day,
    ROUND(100.0 * SUM(CASE WHEN user_id IS NULL THEN 1 ELSE 0 END) / COUNT(*), 1) AS null_pct
FROM read_parquet('demo/fixtures/null_spike/orders.parquet')
GROUP BY 1
ORDER BY 1
''').fetchall()

# Check if any day has >30% NULL rate
has_anomaly = any(row[1] > 30.0 for row in result)
print('ANOMALY_DETECTED' if has_anomaly else 'NO_ANOMALY')
" 2>/dev/null)

if [[ "$ANOMALY_CHECK" == *"ANOMALY_DETECTED"* ]]; then
    pass "NULL spike anomaly detected in fixture"
else
    fail "NULL spike anomaly not found in fixture"
fi

# =============================================================================
# Test 4: Verify DuckDB adapter exists
# =============================================================================
echo ""
echo "[4/7] Checking DuckDB adapter..."

if [ -f "backend/src/dataing/adapters/db/duckdb.py" ]; then
    pass "DuckDB adapter file exists"
else
    fail "DuckDB adapter file missing"
fi

# Check if DuckDB is registered
if grep -q "DuckDBAdapter" backend/src/dataing/adapters/db/__init__.py; then
    pass "DuckDB adapter registered"
else
    fail "DuckDB adapter not registered in __init__.py"
fi

# =============================================================================
# Test 5: Check demo mode in deps.py
# =============================================================================
echo ""
echo "[5/7] Checking demo mode integration..."

if grep -q "DATADR_DEMO_MODE" backend/src/dataing/entrypoints/api/deps.py; then
    pass "Demo mode check present in deps.py"
else
    fail "Demo mode check missing in deps.py"
fi

if grep -q "_seed_demo_data" backend/src/dataing/entrypoints/api/deps.py; then
    pass "Demo seed function present"
else
    fail "Demo seed function missing"
fi

# =============================================================================
# Test 6: Check docker-compose.demo.yml
# =============================================================================
echo ""
echo "[6/7] Checking Docker Compose configuration..."

if [ -f "docker-compose.demo.yml" ]; then
    pass "docker-compose.demo.yml exists"
else
    fail "docker-compose.demo.yml missing"
fi

if grep -q "DATADR_DEMO_MODE" docker-compose.demo.yml; then
    pass "Demo mode configured in Docker Compose"
else
    fail "Demo mode not configured in Docker Compose"
fi

# =============================================================================
# Test 7: Check justfile demo commands
# =============================================================================
echo ""
echo "[7/7] Checking justfile demo commands..."

if grep -q "^demo:" justfile; then
    pass "Demo command in justfile"
else
    fail "Demo command missing in justfile"
fi

if grep -q "demo-fixtures" justfile; then
    pass "Demo-fixtures command in justfile"
else
    fail "Demo-fixtures command missing in justfile"
fi

# =============================================================================
# Summary
# =============================================================================
echo ""
echo "==================================="
echo "         TEST SUMMARY"
echo "==================================="
echo -e "${GREEN}Passed: $PASSED${NC}"
echo -e "${RED}Failed: $FAILED${NC}"
echo ""

if [ $FAILED -eq 0 ]; then
    echo -e "${GREEN}All tests passed!${NC}"
    echo ""
    echo "To run the demo:"
    echo "  just demo"
    echo ""
    echo "Or with Docker:"
    echo "  just demo-docker"
    exit 0
else
    echo -e "${RED}Some tests failed. Please fix the issues above.${NC}"
    exit 1
fi
