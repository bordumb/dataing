#!/bin/bash

# Ensure we are in the project root
if [ ! -d "backend" ]; then
    echo "❌ Error: 'backend' directory not found. Please run this from the project root."
    exit 1
fi

echo "📦 Starting GitLab-style reorganization..."

# 1. Create the CE directory and move EVERYTHING there initially
# This makes CE the default home for all code.
echo "-> Moving current 'backend' into 'ce/backend'..."
mkdir -p ce
mv backend ce/

# 2. Create the EE directory structure
# We mirror the path structure so files overlay correctly later.
echo "-> Creating 'ee' directory structure..."
BASE_EE_PATH="ee/backend/src/dataing"

mkdir -p "$BASE_EE_PATH/adapters/datasource/api"
mkdir -p "$BASE_EE_PATH/adapters/audit"
mkdir -p "$BASE_EE_PATH/adapters/sso"
mkdir -p "$BASE_EE_PATH/core/scim"
mkdir -p "$BASE_EE_PATH/core/sso"
mkdir -p "$BASE_EE_PATH/entrypoints/api/middleware"
mkdir -p "$BASE_EE_PATH/entrypoints/api/routes"
mkdir -p "$BASE_EE_PATH/jobs"
mkdir -p "$BASE_EE_PATH/models"

# 3. Extract Enterprise Features from CE to EE

echo "-> Extracting Enterprise features..."

# --- Connectors (Premium SaaS APIs) ---
# We leave 'base.py' and standard DBs in CE.
mv ce/backend/src/dataing/adapters/datasource/api/hubspot.py "$BASE_EE_PATH/adapters/datasource/api/"
mv ce/backend/src/dataing/adapters/datasource/api/salesforce.py "$BASE_EE_PATH/adapters/datasource/api/"
mv ce/backend/src/dataing/adapters/datasource/api/stripe.py "$BASE_EE_PATH/adapters/datasource/api/"

# --- Audit Logs ---
# Move the entire audit adapter folder
mv ce/backend/src/dataing/adapters/audit/* "$BASE_EE_PATH/adapters/audit/"
rmdir ce/backend/src/dataing/adapters/audit # Clean up empty dir

# Move Audit Middleware and Routes
mv ce/backend/src/dataing/entrypoints/api/middleware/audit.py "$BASE_EE_PATH/entrypoints/api/middleware/"
mv ce/backend/src/dataing/entrypoints/api/routes/audit.py "$BASE_EE_PATH/entrypoints/api/routes/"
mv ce/backend/src/dataing/jobs/audit_cleanup.py "$BASE_EE_PATH/jobs/"
mv ce/backend/src/dataing/models/audit_log.py "$BASE_EE_PATH/models/"

# --- SSO & Identity (SAML/OIDC/SCIM) ---
# Move the entire SSO adapter folder
mv ce/backend/src/dataing/adapters/sso/* "$BASE_EE_PATH/adapters/sso/"
rmdir ce/backend/src/dataing/adapters/sso

# Move Core Business Logic for SSO/SCIM
mv ce/backend/src/dataing/core/scim/* "$BASE_EE_PATH/core/scim/"
rmdir ce/backend/src/dataing/core/scim
mv ce/backend/src/dataing/core/sso/* "$BASE_EE_PATH/core/sso/"
rmdir ce/backend/src/dataing/core/sso

# Move SSO/SCIM Routes
mv ce/backend/src/dataing/entrypoints/api/routes/scim.py "$BASE_EE_PATH/entrypoints/api/routes/"
mv ce/backend/src/dataing/entrypoints/api/routes/sso.py "$BASE_EE_PATH/entrypoints/api/routes/"

# --- Organization Settings ---
# Often considered an EE feature if it controls RBAC/SSO settings
mv ce/backend/src/dataing/entrypoints/api/routes/settings.py "$BASE_EE_PATH/entrypoints/api/routes/"

# 4. Clean up and Finalize
# Ensure EE directories have __init__.py files so they are treated as packages
echo "-> finalizing python packages..."
find ee -type d -exec touch {}/__init__.py \;

echo "✅ Done! You now have 'ce/' and 'ee/' directories."
