#!/bin/bash
# Setup script for architectural governance tools

set -e

echo "=========================================="
echo "Architectural Governance Setup"
echo "=========================================="
echo ""

# Check if we're in the project root
if [ ! -f "pyproject.toml" ]; then
    echo "❌ Error: Must be run from project root"
    exit 1
fi

echo "1. Installing pre-commit..."
pip install pre-commit

echo ""
echo "2. Installing pre-commit hooks..."
pre-commit install

echo ""
echo "3. Running pre-commit on all files (initial check)..."
pre-commit run --all-files || true

echo ""
echo "4. Installing test dependencies..."
pip install pytest pytest-cov

echo ""
echo "5. Running architecture tests..."
pytest tests/architecture/ -v

echo ""
echo "=========================================="
echo "✅ Setup Complete!"
echo "=========================================="
echo ""
echo "Next steps:"
echo ""
echo "1. Read the governance guide:"
echo "   📖 docs/ARCHITECTURAL_GOVERNANCE.md"
echo ""
echo "2. Review contributing guidelines:"
echo "   📖 CONTRIBUTING.md"
echo ""
echo "3. Before committing, ensure:"
echo "   ✅ Pre-commit hooks pass (automatic)"
echo "   ✅ Tests pass: pytest tests/ -v"
echo "   ✅ Architecture tests pass: pytest tests/architecture/ -v"
echo ""
echo "4. Manual checks (optional):"
echo "   python scripts/check_direct_db_access.py"
echo "   python scripts/check_import_patterns.py"
echo "   python scripts/check_repository_usage.py"
echo ""
echo "Happy coding! Remember to follow the patterns."
