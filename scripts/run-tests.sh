#!/usr/bin/env bash
set -euo pipefail

# Run all test suites
# This script runs backend, frontend, and integration tests

echo "🧪 Running all test suites..."

# Track overall status
OVERALL_STATUS=0

# Backend tests
echo ""
echo "=== Backend Tests ==="
if [ -d "backend" ]; then
    if docker compose ps backend 2>/dev/null | grep -q "running"; then
        echo "Running backend tests in container..."
        if docker compose exec -T backend pytest --cov=app --cov-report=term-missing -v; then
            echo "✅ Backend tests passed"
        else
            echo "❌ Backend tests failed"
            OVERALL_STATUS=1
        fi
    else
        echo "⚠️  Backend service not running. Starting..."
        if docker compose up -d backend; then
            sleep 5
            if docker compose exec -T backend pytest --cov=app --cov-report=term-missing -v; then
                echo "✅ Backend tests passed"
            else
                echo "❌ Backend tests failed"
                OVERALL_STATUS=1
            fi
        else
            echo "❌ Failed to start backend service"
            OVERALL_STATUS=1
        fi
    fi
else
    echo "⚠️  No backend directory found, skipping"
fi

# Frontend tests
echo ""
echo "=== Frontend Tests ==="
if [ -d "frontend" ]; then
    cd frontend
    if [ ! -d "node_modules" ]; then
        echo "Installing frontend dependencies..."
        if npm ci; then
            echo "✅ Dependencies installed"
        else
            echo "❌ Failed to install dependencies"
            OVERALL_STATUS=1
            cd ..
            if [ $OVERALL_STATUS -eq 0 ]; then
                echo "✅ All test suites passed"
            else
                echo "❌ Some test suites failed"
                exit 1
            fi
        fi
    fi
    if [ -d "node_modules" ]; then
        echo "Running frontend tests..."
        if npm run test:coverage; then
            echo "✅ Frontend tests passed"
        else
            echo "❌ Frontend tests failed"
            OVERALL_STATUS=1
        fi
    fi
    cd ..
else
    echo "⚠️  No frontend directory found, skipping"
fi

# Integration tests (if they exist)
echo ""
echo "=== Integration Tests ==="
if [ -d "tests/integration" ]; then
    echo "Running integration tests..."
    cd tests/integration
    if [ ! -d "node_modules" ]; then
        if npm ci; then
            echo "✅ Integration test dependencies installed"
        else
            echo "❌ Failed to install integration test dependencies"
            OVERALL_STATUS=1
            cd ../..
            if [ $OVERALL_STATUS -eq 0 ]; then
                echo "✅ All test suites passed"
            else
                echo "❌ Some test suites failed"
                exit 1
            fi
        fi
    fi
    if [ -d "node_modules" ]; then
        if npm test; then
            echo "✅ Integration tests passed"
        else
            echo "❌ Integration tests failed"
            OVERALL_STATUS=1
        fi
    fi
    cd ../..
else
    echo "⚠️  No integration test directory found, skipping"
fi

# Final status
echo ""
if [ $OVERALL_STATUS -eq 0 ]; then
    echo "✅ All test suites passed"
else
    echo "❌ Some test suites failed"
    exit 1
fi
