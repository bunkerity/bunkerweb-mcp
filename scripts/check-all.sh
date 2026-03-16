#!/bin/bash
set -e

echo "🧪 Running test suite..."
OTEL_TRACING_ENABLED=false .venv/bin/pytest tests/ -v

echo ""
echo "✨ Running ruff format..."
.venv/bin/ruff format src/bunkerweb_mcp/

echo ""
echo "🔍 Running ruff check..."
.venv/bin/ruff check src/bunkerweb_mcp/

echo ""
echo "🔎 Running mypy type checking..."
.venv/bin/mypy src/ --strict

echo ""
echo "✅ All checks passed!"
