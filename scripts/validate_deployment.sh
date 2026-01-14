#!/bin/bash
# Deployment Validation Script
# Validates that the Dockerfile dependency installation matches pyproject.toml
# Run this before deploying to catch dependency mismatches early

set -e

echo "🔍 Deployment Validation Script"
echo "================================"

# Check that pyproject.toml exists
if [ ! -f "pyproject.toml" ]; then
    echo "❌ ERROR: pyproject.toml not found"
    exit 1
fi

# Check that Dockerfile exists
if [ ! -f "Dockerfile" ]; then
    echo "❌ ERROR: Dockerfile not found"
    exit 1
fi

# Check that Dockerfile uses automated dependency installation (not manual list)
if grep -q "google-generativeai" Dockerfile && grep -q "python-dotenv" Dockerfile && grep -q "pillow" Dockerfile; then
    echo "❌ ERROR: Dockerfile contains manual dependency list"
    echo "   Dockerfile should use 'uv export' to automatically read from pyproject.toml"
    echo "   Manual dependency lists cause deployment failures when dependencies change"
    echo ""
    echo "   Expected pattern:"
    echo "   RUN uv export --no-dev --no-hashes --frozen > requirements.txt && \\"
    echo "       uv pip install --system --no-cache -r requirements.txt"
    exit 1
fi

# Check that Dockerfile uses uv export pattern
if ! grep -q "uv export" Dockerfile; then
    echo "⚠️  WARNING: Dockerfile does not use 'uv export' pattern"
    echo "   Recommended approach: Generate requirements.txt from pyproject.toml"
else
    echo "✅ Dockerfile uses automated dependency installation (uv export)"
fi

# Build test: Try to build the Docker image (optional, slow)
if [ "${RUN_DOCKER_BUILD_TEST:-false}" = "true" ]; then
    echo ""
    echo "🐳 Running Docker build test (this may take a few minutes)..."
    if docker build --target=test -t deployment-test:latest . > /dev/null 2>&1; then
        echo "✅ Docker build succeeded"
    else
        echo "❌ ERROR: Docker build failed"
        echo "   Run 'docker build -t deployment-test:latest .' to see full error"
        exit 1
    fi
fi

# Check that all app imports can be resolved
echo ""
echo "🔍 Checking Python imports..."

# Create a temporary virtual environment with production dependencies
TEMP_VENV=$(mktemp -d)
uv venv "$TEMP_VENV" --quiet
source "$TEMP_VENV/bin/activate"

# Install production dependencies
uv pip install --quiet -r <(uv export --no-dev --no-hashes)

# Check that app can be imported
if python -c "from app import main" 2>/dev/null; then
    echo "✅ All app imports resolved successfully"
else
    echo "❌ ERROR: Failed to import app.main"
    echo "   This indicates missing dependencies or import errors"
    deactivate
    rm -rf "$TEMP_VENV"
    exit 1
fi

# Cleanup
deactivate
rm -rf "$TEMP_VENV"

echo ""
echo "✅ All deployment validation checks passed!"
echo ""
echo "Next steps:"
echo "1. Commit changes to git"
echo "2. Push to Railway deployment branch"
echo "3. Monitor Railway logs for startup errors"
