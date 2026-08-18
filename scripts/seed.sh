#!/usr/bin/env bash
set -euo pipefail

# Seed the database with the Golden Dataset (business entities + Golden RAG corpus).
# This script creates synthetic deterministic data for the ForgeMind application.

echo "🌱 Seeding database with golden dataset..."

# Guard: authoritative seed package path (backend/app/seed).
if [ ! -d "backend/app/seed" ]; then
    echo "❌ Seed module not found at backend/app/seed"
    exit 1
fi

# Check if backend container is running
if ! docker compose ps backend 2>/dev/null | grep -q "running"; then
    echo "❌ Backend service is not running. Start services first:"
    echo "   docker compose up -d"
    exit 1
fi

# Run seed command (authoritative module path; triggers business seeding and
# the deterministic Golden RAG corpus ingestion via the existing bridge)
if docker compose exec -T backend python -m app.seed.generator.main; then
    echo "✅ Seed completed successfully"
else
    echo "❌ Seed failed"
    exit 1
fi
