#!/bin/bash
set -e

echo "🧹 Cleaning up..."
rm -rf node_modules .next

echo ""
echo "📦 Installing dependencies..."
pnpm install --frozen-lockfile

echo ""
echo "✅ Running ESLint..."
pnpm lint

echo ""
echo "🔍 Running TypeScript type check..."
pnpm typecheck

echo ""
echo "🏗️  Building Next.js application..."
pnpm build

echo ""
echo "✅ All CI checks passed locally!"
