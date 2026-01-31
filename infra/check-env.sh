#!/bin/bash
# Validate required environment variables for Dataing
# Run before docker compose up to catch configuration issues

set -e

RED='\033[0;31m'
YELLOW='\033[1;33m'
GREEN='\033[0;32m'
NC='\033[0m' # No Color

errors=0
warnings=0

echo "Checking Dataing environment configuration..."
echo ""

# Required variables
if [ -z "$ANTHROPIC_API_KEY" ]; then
    echo -e "${RED}ERROR: ANTHROPIC_API_KEY is not set${NC}"
    echo "  Investigations require an Anthropic API key to function."
    echo "  Get your key at: https://console.anthropic.com"
    echo ""
    errors=$((errors + 1))
fi

if [ -z "$DATADR_ENCRYPTION_KEY" ]; then
    echo -e "${RED}ERROR: DATADR_ENCRYPTION_KEY is not set${NC}"
    echo "  Datasource credentials cannot be stored without an encryption key."
    echo "  Generate with: python -c \"from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())\""
    echo ""
    errors=$((errors + 1))
fi

# Security warnings
if [ "$POSTGRES_PASSWORD" = "dataing" ] || [ -z "$POSTGRES_PASSWORD" ]; then  # pragma: allowlist secret
    echo -e "${YELLOW}WARNING: POSTGRES_PASSWORD is using default value${NC}"
    echo "  Change this in production for security."
    echo ""
    warnings=$((warnings + 1))
fi

# Summary
echo "----------------------------------------"
if [ $errors -gt 0 ]; then
    echo -e "${RED}Configuration check failed: $errors error(s), $warnings warning(s)${NC}"
    echo "Fix the errors above before running docker compose up"
    exit 1
elif [ $warnings -gt 0 ]; then
    echo -e "${YELLOW}Configuration check passed with $warnings warning(s)${NC}"
    echo "Consider fixing warnings before production deployment"
    exit 0
else
    echo -e "${GREEN}Configuration check passed${NC}"
    exit 0
fi
