.PHONY: help setup test lint format typecheck check clean

PYTHON ?= python3
VENV ?= .venv
BIN ?= $(if $(wildcard $(VENV)/bin/python),$(VENV)/bin/,$(if $(VIRTUAL_ENV),$(VIRTUAL_ENV)/bin/,))

help:
	@echo "Available targets:"
	@echo "  make setup      - Idempotent environment setup (venv + dependencies + pre-commit)"
	@echo "  make test       - Run automated test suite (pytest -q)"
	@echo "  make lint       - Run ruff linter check"
	@echo "  make format     - Run ruff format check"
	@echo "  make typecheck  - Run mypy static type analysis"
	@echo "  make check      - Run lint, typecheck, and fast release tests"
	@echo "  make clean      - Remove build/cache artifacts"

setup:
	@./scripts/setup.sh

test:
	$(BIN)python -m pytest -q

lint:
	$(BIN)ruff check histra

format:
	$(BIN)ruff format --check histra

typecheck:
	$(BIN)mypy

check: lint typecheck
	$(BIN)python -m pytest -q histra/tests/test_backend_coverage_enforcement.py histra/tests/test_article_models_benchmark.py histra/tests/test_package_metadata.py histra/tests/test_backend_api.py

clean:
	rm -rf build/ dist/ *.egg-info .pytest_cache/ .ruff_cache/ .mypy_cache/
	find . -type d -name "__pycache__" -exec rm -rf {} +
