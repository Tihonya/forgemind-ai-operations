.PHONY: help dev test lint seed reset deploy clean compose-validate config-validate backup-smoke smoke-prepare caddy-validate

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
	@if [ ! -d "backend/app/seed" ]; then \
		echo "⚠️  Seed module not found at backend/app/seed"; \
		exit 1; \
	fi
	docker compose exec backend python -m app.seed.generator.main
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

acceptance-verify: ## Run acceptance harness in implementation-verification mode (Phase B)
	@echo "Running acceptance harness (verification mode)..."
	python scripts/acceptance_harness.py --mode=verify
	@echo "Verification complete."

acceptance-formal: ## Run acceptance harness in formal-evidence mode (Phase C — requires PO authorization)
	@echo "Running acceptance harness (formal-evidence mode)..."
	python scripts/acceptance_harness.py --mode=formal
	@echo "Formal evidence collected. See evidence/ directory."

compose-validate: ## Validate production Compose resolves with the template env (WP-P7-02)
	@echo "Validating production compose with non-secret template env..."
	cp infra/prod.env.example /tmp/forgemind-prod.env.template
	docker compose --env-file /tmp/forgemind-prod.env.template \
		-f docker-compose.prod.yml config --quiet
	@echo "Production compose configuration valid."

caddy-validate: ## Validate the production Caddyfile with safe placeholder env (WP-P7-02)
	@echo "Validating production Caddyfile with safe placeholder env..."
	docker run --rm -e CADDY_DOMAIN=example.com -e CADDY_EMAIL=ops@example.com \
		-v "$(CURDIR)/infra/caddy/Caddyfile:/etc/caddy/Caddyfile:ro" \
		caddy:2-alpine caddy validate --config /etc/caddy/Caddyfile --adapter caddyfile
	@echo "Caddyfile valid."

config-validate: ## Fail-closed production configuration validation (WP-P7-02)
	cd backend && ../.venv/bin/python3.12 -m app.ops.validate_config

backup-smoke: ## Run repo-owned backup/healthcheck shell test suites (WP-P7-02)
	bash scripts/tests/test_backup.sh
	bash scripts/tests/test_backup_cycle.sh
	bash scripts/tests/test_worker_healthcheck.sh

smoke-prepare: ## Offline embedding smoke preparation (NO live provider call)
	cd backend && ../.venv/bin/python3.12 -m app.ops.embedding_smoke
