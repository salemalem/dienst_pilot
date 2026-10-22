COMPOSE := docker compose -f infra/compose.dev.yml
SEED ?= 20261020
SEED_DIR := data/synthetic/v1

.PHONY: install dev down logs seed test e2e screenshots lint format api-client eval tune train labels

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

seed: ## Rebuild the dev database from the seed (also after the app wrote to it): generate (if changed), drop the schemas, migrate, load
	$(COMPOSE) up -d --wait postgres
	uv run python -m synthdata generate --seed $(SEED) --out $(SEED_DIR) --if-changed
	DEMO_MODE=true uv run python -m dienstpilot.seeding --reset
	cd backend && uv run alembic upgrade head
	uv run python -m dienstpilot.seeding $(SEED_DIR)

test: ## Python and TypeScript tests
	uv run pytest
	pnpm test

e2e: ## Playwright e2e on the demo clock: dashboard (:3100) and staff app on Expo web (:8083), own database dienstpilot_e2e, API on :8100
	$(COMPOSE) up -d --wait postgres redis
	$(COMPOSE) exec -T postgres psql -U dienstpilot -c "CREATE DATABASE dienstpilot_e2e" 2>/dev/null || true
	pnpm build:packages
	pnpm --filter @dienstpilot/dashboard e2e
	pnpm --filter @dienstpilot/mobile e2e

screenshots: ## Regenerate screenshots/ (DE and EN, each on a fresh seed): images, contact sheets, INDEX.md
	$(COMPOSE) up -d --wait postgres redis
	$(COMPOSE) exec -T postgres psql -U dienstpilot -c "CREATE DATABASE dienstpilot_e2e" 2>/dev/null || true
	pnpm build:packages
	pnpm --filter @dienstpilot/mobile build:e2e
	rm -rf screenshots/de screenshots/en screenshots/manifest.json screenshots/INDEX.md
	E2E_LANG=de pnpm --filter @dienstpilot/screenshots capture
	E2E_LANG=en SCREENSHOTS_SKIP_BUILD=1 pnpm --filter @dienstpilot/screenshots capture
	pnpm --filter @dienstpilot/screenshots finalize

lint: ## ruff, mypy, import-linter, eslint, tsc, prettier
	uv run ruff check backend ml
	uv run ruff format --check backend ml
	uv run mypy
	uv run lint-imports
	pnpm lint
	pnpm format:check

format: ## Apply ruff and prettier formatting
	uv run ruff format backend ml
	uv run ruff check --fix backend ml
	pnpm format

CAFFEINATE := $(shell command -v caffeinate >/dev/null 2>&1 && echo "caffeinate -i")

labels: ## C6 labels: solver runs on simulated leave requests (about an hour, resumable; the Mac stays awake)
	$(CAFFEINATE) uv run python eval/run_c6_labels.py --split train
	$(CAFFEINATE) uv run python eval/run_c6_labels.py --split test
	$(CAFFEINATE) uv run python eval/run_c6_labels.py --fidelity 200
	uv run python eval/run_c6_labels.py --sample
	uv run python eval/run_c6_labels.py --seal

train: ## C3, C4, C5 and C6: rolling-origin CV on 2021-2024, fit the candidates, log and register them in the local MLflow (ml/mlflow)
	uv run python -m dienstpilot_ml.training --data $(SEED_DIR)
	uv run python -m dienstpilot_ml.training.c4 --data $(SEED_DIR)
	uv run python -m dienstpilot_ml.training.c5 --data $(SEED_DIR)
	uv run python -m dienstpilot_ml.training.c6

eval: ## Validator eval, full benchmark (2025, about 10 min), ARCHITECTURE §17.1 table, C3, C4, C5 and C6 (runs make train first; C6 reads the committed labels, `make labels` rebuilds them)
	uv run python eval/run_validator_eval.py --data $(SEED_DIR)
	uv run python eval/run_benchmark.py --data $(SEED_DIR)
	uv run python eval/render_tables.py
	$(MAKE) train
	uv run python eval/run_c3_eval.py --data $(SEED_DIR)
	uv run python eval/run_c4_eval.py --data $(SEED_DIR)
	uv run python eval/run_c5_eval.py --data $(SEED_DIR)
	-C6_WRITE_LATENCY=1 uv run pytest backend/tests/api/test_leave_hint.py -k endpoint_latency -q
	uv run python eval/run_c6_eval.py --data $(SEED_DIR)

tune: ## Re-tune the balanced profile on July-December 2024 (eval/results/tuning.json)
	uv run python eval/tune_profiles.py --data $(SEED_DIR)

api-client: ## Regenerate packages/api-client from the backend's OpenAPI schema
	pnpm --filter @dienstpilot/api-client generate
