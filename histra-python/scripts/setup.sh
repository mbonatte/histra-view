#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "${REPO_ROOT}"

echo "=== HiStrA-Python Environment Setup ==="

PYTHON_BIN="${PYTHON:-python3}"
if ! command -v "${PYTHON_BIN}" >/dev/null 2>&1; then
    echo "Error: Python interpreter '${PYTHON_BIN}' not found." >&2
    exit 1
fi

if [ -z "${VIRTUAL_ENV:-}" ]; then
    if [ ! -d ".venv" ]; then
        echo "Creating virtual environment in .venv..."
        "${PYTHON_BIN}" -m venv .venv
    fi
    echo "Activating .venv..."
    # shellcheck disable=SC1091
    source .venv/bin/activate
fi

echo "Upgrading pip..."
python -m pip install --upgrade pip

echo "Installing histra-python with dev dependencies..."
python -m pip install -e ".[dev]"

if command -v pre-commit >/dev/null 2>&1 && [ -d ".git" ]; then
    echo "Installing pre-commit hooks..."
    pre-commit install || true
fi

echo "=== Setup complete! ==="
echo "Run 'make check' or 'pytest -q' to verify your installation."
