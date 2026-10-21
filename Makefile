COMPOSE := docker compose -f infra/compose.dev.yml
SEED ?= 20261020
SEED_DIR := data/synthetic/v1

.PHONY: install dev down logs seed test lint format api-client

install: ## Install Python and Node dependencies
	uv sync
	pnpm install

dev: install ## Start Postgres, Redis and the API (Docker), then the dashboard (:3000) and Expo web (:8081)
	$(COMPOSE) up -d --build --wait
	@echo "API ready on http://localhost:8000/health/ready"
	pnpm dev

down: ## Stop the Docker services
	$(COMPOSE) down

logs: ## Follow the API, Postgres and Redis logs
	$(COMPOSE) logs -f

seed: ## Rebuild the database from the seed: generate (if changed), reset the schema, load
	$(COMPOSE) up -d --wait postgres
	uv run python -m synthdata generate --seed $(SEED) --out $(SEED_DIR) --if-changed
	cd backend && uv run alembic downgrade base && uv run alembic upgrade head
	uv run python -m dienstpilot.seeding $(SEED_DIR)

test: ## Python and TypeScript tests
	uv run pytest
	pnpm test

lint: ## ruff, mypy, import-linter, eslint, tsc, prettier
	uv run ruff check backend
	uv run ruff format --check backend
	uv run mypy
	uv run lint-imports
	pnpm lint
	pnpm format:check

format: ## Apply ruff and prettier formatting
	uv run ruff format backend
	uv run ruff check --fix backend
	pnpm format

api-client: ## Regenerate packages/api-client from the backend's OpenAPI schema
	pnpm --filter @dienstpilot/api-client generate
