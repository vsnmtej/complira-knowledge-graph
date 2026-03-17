.PHONY: help test test-unit test-integration test-parser test-all test-cov clean install lint format

help: ## Show this help message
	@echo 'Usage: make [target]'
	@echo ''
	@echo 'Available targets:'
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-20s\033[0m %s\n", $$1, $$2}'

install: ## Install dependencies
	pip install -e .
	pip install pytest pytest-cov pytest-asyncio pytest-mock pytest-xdist ruff mypy

test: test-unit ## Run unit tests (default)

test-unit: ## Run unit tests only
	pytest tests/unit/ -v --tb=short -m "not slow"

test-integration: ## Run integration tests only (requires database)
	pytest tests/integration/ -v --tb=short -m "integration and not slow"

test-parser: ## Run parser verification script
	python test_scan_fixes.py

test-all: ## Run all tests (unit + integration + parser)
	pytest tests/ -v --tb=short -m "not slow"
	python test_scan_fixes.py

test-cov: ## Run tests with coverage report
	pytest tests/unit/ tests/integration/ -v \
		--cov=src \
		--cov=complira_graph \
		--cov-report=html \
		--cov-report=term-missing \
		--cov-report=xml \
		-m "not slow"
	@echo ""
	@echo "Coverage report generated in htmlcov/index.html"

test-scan: ## Run scan ingestion tests specifically
	pytest tests/unit/test_cyclonedx_parser.py -v
	pytest tests/integration/test_scan_ingestion_api.py -v
	python test_scan_fixes.py

test-contract: ## Run API contract tests (validates mocks match schema)
	pytest tests/contract/test_api_contract.py -v

generate-mocks: ## Generate API mock responses for frontend testing
	python scripts/generate_api_mocks.py

test-watch: ## Run tests in watch mode (re-run on file changes)
	pytest tests/unit/ -v -f --tb=short

lint: ## Run linter (ruff)
	ruff check src/ tests/

lint-fix: ## Run linter and fix issues automatically
	ruff check --fix src/ tests/

format: ## Format code with ruff
	ruff format src/ tests/

typecheck: ## Run type checker (mypy)
	mypy src/ --ignore-missing-imports

quality: lint typecheck ## Run all code quality checks

clean: ## Clean up generated files
	rm -rf .pytest_cache
	rm -rf htmlcov
	rm -rf .coverage
	rm -rf coverage.xml
	rm -rf .ruff_cache
	rm -rf .mypy_cache
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -type f -name "*.pyc" -delete

server: ## Start development server
	.venv/bin/uvicorn src.api.main:app --reload --port 8000

server-prod: ## Start production server
	.venv/bin/uvicorn src.api.main:app --host 0.0.0.0 --port 8000 --workers 4

db-start: ## Start local databases (docker-compose)
	docker-compose up -d arangodb redis

db-stop: ## Stop local databases
	docker-compose down

db-reset: ## Reset local databases (WARNING: deletes all data)
	docker-compose down -v
	docker-compose up -d arangodb redis

# CI/CD simulation targets
ci-test: ## Run tests as CI would (fast)
	pytest tests/unit/ -v -m "not slow" --maxfail=5
	python test_scan_fixes.py

ci-full: ## Run full CI pipeline locally
	@echo "Running code quality checks..."
	ruff check src/ tests/ || true
	mypy src/ --ignore-missing-imports || true
	@echo ""
	@echo "Running unit tests..."
	pytest tests/unit/ -v --cov=src --cov=complira_graph -m "not slow"
	@echo ""
	@echo "Running parser verification..."
	python test_scan_fixes.py
	@echo ""
	@echo "✅ CI pipeline simulation complete"

# Docker targets
docker-build: ## Build Docker image
	docker build -t complira-api:latest .

docker-run: ## Run Docker container locally
	docker run -p 8000:8000 complira-api:latest

docker-test: ## Run tests in Docker container
	docker build -t complira-api:test --target test .
	docker run complira-api:test
