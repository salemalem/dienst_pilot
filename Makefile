COMPOSE := docker compose -f infra/compose.dev.yml

.PHONY: install dev down logs test lint format api-client

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
