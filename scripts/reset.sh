#!/usr/bin/env bash
set -euo pipefail

# Reset demo data
# This script resets the database to initial state with golden dataset

echo "🔄 Resetting demo data..."

# Guard: reset service not yet implemented in Phase 0
if [ ! -f "backend/app/services/reset_service.py" ]; then
    echo "⚠️  Reset service not yet implemented (deferred to Phase 1)"
    exit 0
fi

# Safety check
if [ "${FORCE_RESET:-}" != "true" ]; then
    echo "⚠️  This will reset all data. Continue? (y/N)"
    read -r response
    if [[ ! "$response" =~ ^[Yy]$ ]]; then
        echo "❌ Reset cancelled"
        exit 0
    fi
fi

# Check if backend container is running
if ! docker compose ps backend 2>/dev/null | grep -q "running"; then
    echo "❌ Backend service is not running. Start services first:"
    echo "   docker compose up -d"
    exit 1
fi

# Run reset command
if docker compose exec -T backend python -m app.services.reset_service; then
    echo "✅ Reset completed successfully"
else
    echo "❌ Reset failed"
    exit 1
fi
