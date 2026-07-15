#!/usr/bin/env bash
set -euo pipefail

# Check for secrets in codebase
# This script scans for accidentally committed secrets

echo "🔍 Checking for secrets in codebase..."

# Patterns to detect
PATTERNS=(
    "sk_live_[a-zA-Z0-9]+"
    "sk_test_[a-zA-Z0-9]+"
    "ghp_[a-zA-Z0-9]{36}"
    "gho_[a-zA-Z0-9]{36}"
    "ghu_[a-zA-Z0-9]{36}"
    "ghs_[a-zA-Z0-9]{36}"
    "ghr_[a-zA-Z0-9]{36}"
    "AIza[a-zA-Z0-9_-]{35}"
    "-----BEGIN PRIVATE KEY-----"
    "-----BEGIN RSA PRIVATE KEY-----"
    "-----BEGIN EC PRIVATE KEY-----"
    "-----BEGIN OPENSSH PRIVATE KEY-----"
    "password\s*=\s*['\"][^'\"]{8,}['\"]"
    "api_key\s*=\s*['\"][^'\"]+['\"]"
    "secret\s*=\s*['\"][^'\"]+['\"]"
)

# Files/directories to exclude
EXCLUDE_PATTERN="node_modules|\.git|\.venv|venv|__pycache__|\.pytest_cache|coverage|dist|build"

FOUND_SECRETS=0

# Check staged files (for pre-commit)
if git rev-parse --is-inside-work-tree >/dev/null 2>&1; then
    echo "Checking staged files..."
    STAGED_FILES=$(git diff --cached --name-only --diff-filter=ACM 2>/dev/null || echo "")

    if [ -n "$STAGED_FILES" ]; then
        for pattern in "${PATTERNS[@]}"; do
            if echo "$STAGED_FILES" | grep -vE "$EXCLUDE_PATTERN" | xargs grep -E "$pattern" 2>/dev/null; then
                echo "❌ Potential secret found in staged files matching pattern: $pattern"
                FOUND_SECRETS=1
            fi
        done
    fi
fi

# Check all tracked files
echo "Checking all tracked files..."
for pattern in "${PATTERNS[@]}"; do
    if git grep -E "$pattern" -- ':!node_modules' ':!*.lock' ':!.env' ':!.env.example' 2>/dev/null; then
        echo "❌ Potential secret found matching pattern: $pattern"
        FOUND_SECRETS=1
    fi
done

# Check for .env files
echo "Checking for .env files..."
if git ls-files | grep -E "^\.env$|\.env\.local$|\.env\.production$" >/dev/null; then
    echo "❌ .env file found in repository"
    FOUND_SECRETS=1
fi

# Check for private keys
echo "Checking for private key files..."
if git ls-files | grep -E "\.(pem|key|cert)$" >/dev/null; then
    echo "❌ Private key file found in repository"
    FOUND_SECRETS=1
fi

# Final status
echo ""
if [ $FOUND_SECRETS -eq 0 ]; then
    echo "✅ No secrets detected"
    exit 0
else
    echo "❌ Secrets detected! Remove them before committing."
    echo "   Consider using .gitignore for sensitive files."
    echo "   Use environment variables or secret management tools."
    exit 1
fi
