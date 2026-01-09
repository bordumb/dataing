#!/bin/bash
set -euo pipefail

# CE/EE Reorganization Script
# Moves backend/ to dataing/ (CE) and extracts enterprise features to dataing-ee/

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"

cd "$PROJECT_ROOT"

# Safety check
if [ ! -d "backend" ]; then
    echo "Error: 'backend' directory not found. Run from project root."
    exit 1
fi

if [ -d "dataing" ] || [ -d "dataing-ee" ]; then
    echo "Error: 'dataing' or 'dataing-ee' already exists. Clean up first."
    exit 1
fi

echo "Starting CE/EE reorganization..."

# ============================================
# Step 1: Rename backend/ to dataing/ (CE)
# ============================================
echo "-> Renaming backend/ to dataing/..."
mv backend dataing

# ============================================
# Step 2: Create dataing-ee/ structure
# ============================================
echo "-> Creating dataing-ee/ structure..."

# Source directories
mkdir -p dataing-ee/src/dataing_ee/adapters/datasource/api
mkdir -p dataing-ee/src/dataing_ee/adapters/audit
mkdir -p dataing-ee/src/dataing_ee/adapters/sso
mkdir -p dataing-ee/src/dataing_ee/core/scim
mkdir -p dataing-ee/src/dataing_ee/core/sso
mkdir -p dataing-ee/src/dataing_ee/entrypoints/api/middleware
mkdir -p dataing-ee/src/dataing_ee/entrypoints/api/routes
mkdir -p dataing-ee/src/dataing_ee/jobs
mkdir -p dataing-ee/src/dataing_ee/models

# Test directories
mkdir -p dataing-ee/tests/unit/core/scim
mkdir -p dataing-ee/tests/unit/core/sso
mkdir -p dataing-ee/tests/unit/adapters/sso
mkdir -p dataing-ee/tests/unit/adapters/audit
mkdir -p dataing-ee/tests/unit/entrypoints/api/routes

# ============================================
# Step 3: Move EE source files
# ============================================
echo "-> Moving enterprise source files..."

# Premium API connectors
mv dataing/src/dataing/adapters/datasource/api/hubspot.py dataing-ee/src/dataing_ee/adapters/datasource/api/
mv dataing/src/dataing/adapters/datasource/api/salesforce.py dataing-ee/src/dataing_ee/adapters/datasource/api/
mv dataing/src/dataing/adapters/datasource/api/stripe.py dataing-ee/src/dataing_ee/adapters/datasource/api/

# Audit adapters (entire directory)
mv dataing/src/dataing/adapters/audit/* dataing-ee/src/dataing_ee/adapters/audit/
rmdir dataing/src/dataing/adapters/audit

# SSO adapters (entire directory)
mv dataing/src/dataing/adapters/sso/* dataing-ee/src/dataing_ee/adapters/sso/
rmdir dataing/src/dataing/adapters/sso

# Core SCIM (entire directory)
mv dataing/src/dataing/core/scim/* dataing-ee/src/dataing_ee/core/scim/
rmdir dataing/src/dataing/core/scim

# Core SSO (entire directory)
mv dataing/src/dataing/core/sso/* dataing-ee/src/dataing_ee/core/sso/
rmdir dataing/src/dataing/core/sso

# Audit middleware
mv dataing/src/dataing/entrypoints/api/middleware/audit.py dataing-ee/src/dataing_ee/entrypoints/api/middleware/

# EE routes
mv dataing/src/dataing/entrypoints/api/routes/audit.py dataing-ee/src/dataing_ee/entrypoints/api/routes/
mv dataing/src/dataing/entrypoints/api/routes/sso.py dataing-ee/src/dataing_ee/entrypoints/api/routes/
mv dataing/src/dataing/entrypoints/api/routes/scim.py dataing-ee/src/dataing_ee/entrypoints/api/routes/
mv dataing/src/dataing/entrypoints/api/routes/settings.py dataing-ee/src/dataing_ee/entrypoints/api/routes/

# Audit cleanup job
mv dataing/src/dataing/jobs/audit_cleanup.py dataing-ee/src/dataing_ee/jobs/

# Audit log model
mv dataing/src/dataing/models/audit_log.py dataing-ee/src/dataing_ee/models/

# ============================================
# Step 4: Move EE test files
# ============================================
echo "-> Moving enterprise test files..."

# Core SCIM tests
mv dataing/tests/unit/core/scim/* dataing-ee/tests/unit/core/scim/
rmdir dataing/tests/unit/core/scim

# Core SSO tests
mv dataing/tests/unit/core/sso/* dataing-ee/tests/unit/core/sso/
rmdir dataing/tests/unit/core/sso

# Adapter SSO tests
mv dataing/tests/unit/adapters/sso/* dataing-ee/tests/unit/adapters/sso/
rmdir dataing/tests/unit/adapters/sso

# Adapter audit tests
mv dataing/tests/unit/adapters/audit/* dataing-ee/tests/unit/adapters/audit/
rmdir dataing/tests/unit/adapters/audit

# Route tests
mv dataing/tests/unit/entrypoints/api/routes/test_sso.py dataing-ee/tests/unit/entrypoints/api/routes/
mv dataing/tests/unit/entrypoints/api/routes/test_scim.py dataing-ee/tests/unit/entrypoints/api/routes/
mv dataing/tests/unit/entrypoints/api/routes/test_audit.py dataing-ee/tests/unit/entrypoints/api/routes/

# ============================================
# Step 5: Create __init__.py files
# ============================================
echo "-> Creating __init__.py files..."

# Root package
cat > dataing-ee/src/dataing_ee/__init__.py << 'EOF'
"""Dataing Enterprise Edition."""

__version__ = "2.0.0"
EOF

# Create empty __init__.py in all directories
find dataing-ee/src/dataing_ee -type d -exec sh -c 'touch "$1/__init__.py" 2>/dev/null || true' _ {} \;
find dataing-ee/tests -type d -exec sh -c 'touch "$1/__init__.py" 2>/dev/null || true' _ {} \;

# ============================================
# Step 6: Create conftest.py for EE tests
# ============================================
echo "-> Creating test configuration..."

cat > dataing-ee/tests/conftest.py << 'EOF'
"""Pytest configuration for dataing-ee tests."""

import sys
from pathlib import Path

# Add CE package to path for imports
ce_src = Path(__file__).parent.parent.parent / "dataing" / "src"
if str(ce_src) not in sys.path:
    sys.path.insert(0, str(ce_src))
EOF

# ============================================
# Done
# ============================================
echo ""
echo "Reorganization complete!"
echo ""
echo "Structure:"
echo "  dataing/          <- CE (was backend/)"
echo "  dataing-ee/       <- EE (new)"
echo "  frontend/         <- unchanged"
echo ""
echo "Next steps:"
echo "  1. Create dataing/pyproject.toml"
echo "  2. Create dataing-ee/pyproject.toml"
echo "  3. Update root pyproject.toml"
echo "  4. Run: uv run ruff check --fix"
echo "  5. Run: uv run mypy"
echo "  6. Run: uv run pytest"
