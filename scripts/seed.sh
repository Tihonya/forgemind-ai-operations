#!/usr/bin/env bash
set -euo pipefail

# Seed the database with golden dataset
# This script creates synthetic data for the ForgeMind application

echo "🌱 Seeding database with golden dataset..."

# Guard: seed module not yet implemented in Phase 0
if [ ! -d "seed/generator" ]; then
    echo "⚠️  Seed module not yet implemented (deferred to Phase 1)"
    exit 0
fi

# Check if backend container is running
if ! docker compose ps backend 2>/dev/null | grep -q "running"; then
    echo "❌ Backend service is not running. Start services first:"
    echo "   docker compose up -d"
    exit 1
fi

# Run seed command
if docker compose exec -T backend python -m seed.generator.main; then
    echo "✅ Seed completed successfully"
else
    echo "❌ Seed failed"
    exit 1
fi
