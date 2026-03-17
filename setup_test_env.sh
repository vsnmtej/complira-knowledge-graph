#!/bin/bash
# Stage 7: Test Environment Setup Script
# This script installs pytest and dev dependencies for Phase 3A testing

set -e  # Exit on error

echo "========================================="
echo "Phase 3A: Test Environment Setup"
echo "========================================="
echo ""

# Check if uv is installed
if command -v uv &> /dev/null; then
    echo "✅ Found uv package manager"
    echo "Installing dependencies with uv..."
    uv sync --all-extras
    echo "✅ Dependencies installed successfully"
    echo ""
    echo "To activate virtual environment:"
    echo "  source .venv/bin/activate"
else
    echo "⚠️  uv not found, using pip fallback"
    echo ""

    # Check if we're in a virtual environment
    if [[ -z "$VIRTUAL_ENV" ]]; then
        echo "Creating new virtual environment..."
        python3 -m venv .venv-test
        source .venv-test/bin/activate
        echo "✅ Virtual environment created and activated"
    else
        echo "✅ Already in virtual environment: $VIRTUAL_ENV"
    fi

    echo ""
    echo "Installing dev dependencies..."

    # Install pytest and test dependencies
    pip install -q pytest pytest-mock pytest-cov pytest-asyncio pytest-xdist responses

    # Install project in editable mode with dependencies
    pip install -q -e .

    echo "✅ Dependencies installed successfully"
    echo ""
    echo "Virtual environment: .venv-test"
    echo "To activate:"
    echo "  source .venv-test/bin/activate"
fi

echo ""
echo "========================================="
echo "Verify Installation"
echo "========================================="

# Verify pytest is available
if python -m pytest --version &> /dev/null; then
    echo "✅ pytest installed:"
    python -m pytest --version
else
    echo "❌ pytest installation failed"
    exit 1
fi

echo ""
echo "========================================="
echo "Next Steps"
echo "========================================="
echo ""
echo "1. Run unit tests:"
echo "   python -m pytest tests/unit/test_vulncheck_agents.py -v"
echo ""
echo "2. Verify canary endpoint:"
echo "   python test_canary_endpoint.py"
echo ""
echo "3. Initialize database schema:"
echo "   python -m complira_graph.db init_schema"
echo ""
echo "4. See full testing guide:"
echo "   cat tickets/in-progress/phase-3-vulncheck-integration/stage-7-testing-guide.md"
echo ""
