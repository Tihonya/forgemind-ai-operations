.PHONY: help dev test lint seed reset deploy clean

help: ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-20s\033[0m %s\n", $$1, $$2}'

dev: ## Start all services in development mode
	docker compose -f docker-compose.yml -f docker-compose.dev.yml up -d

test: ## Run all test suites
	@echo "Running backend tests..."
	cd backend && ../.venv/bin/pytest -v
	@echo "Running frontend tests..."
	cd frontend && npm test
	@echo "All tests passed."

lint: ## Run all linters
	@echo "Backend linting..."
	cd backend && ../.venv/bin/ruff check .
	cd backend && ../.venv/bin/mypy app/
	@echo "Frontend linting..."
	cd frontend && npm run lint
	@echo "All linters passed."

seed: ## Seed the database with golden dataset (Phase 1+)
	@echo "Seeding database..."
	@if [ ! -d "seed/generator" ]; then \
		echo "⚠️  Seed module not yet implemented (deferred to Phase 1)"; \
		exit 0; \
	fi
	docker compose exec backend python -m seed.generator.main
	@echo "Seed complete."

reset: ## Reset demo data (admin only) (Phase 1+)
	@echo "Resetting demo data..."
	@if [ ! -f "backend/app/services/reset_service.py" ]; then \
		echo "⚠️  Reset service not yet implemented (deferred to Phase 1)"; \
		exit 0; \
	fi
	docker compose exec backend python -m app.services.reset_service
	@echo "Reset complete."

deploy: ## Deploy to production
	@echo "Building and deploying..."
	docker compose -f docker-compose.yml up -d --build
	@echo "Deployment complete."

clean: ## Remove all containers, volumes, and build artifacts
	docker compose down -v
	rm -rf .venv
	rm -rf backend/__pycache__ backend/.pytest_cache backend/.ruff_cache backend/.mypy_cache
	rm -rf frontend/node_modules frontend/dist
	rm -rf infra/caddy/data infra/caddy/config
	@echo "Clean complete."

check-secrets: ## Run secret detection
	./scripts/check-secrets.sh

smoke-test: ## Run smoke tests on running services
	@echo "Running smoke tests..."
	./scripts/run-tests.sh
	@echo "Smoke tests passed."
