#!/bin/bash
set -e

echo "✅ Running ESLint..."
pnpm lint

echo ""
echo "🔍 Running TypeScript type check..."
pnpm typecheck

echo ""
echo "🏗️  Building Next.js application..."
pnpm build

echo ""
echo "✅ All CI checks passed!"
