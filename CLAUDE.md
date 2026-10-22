# CLAUDE.md: DienstPilot

## What this project is

DienstPilot (KI-gestützte Dienstplanung für Kliniken / AI-assisted duty scheduling for hospitals) proposes monthly duty rosters for hospital departments, handles leave requests, shift swaps and sick-call cover, and produces compliance documentation for payroll and the works council. **The AI proposes; a responsible physician approves.**

Source-of-truth documents. Read the relevant one before any task:

- `docs/PROCESS.md`: how the product is used day to day (roles, approvals, monthly cycle, three core situations)
- `docs/ARCHITECTURE.md`: technical design, the eight intelligence components (C1–C8), data, MCP, RAG, MLOps, compliance
- `docs/UI_SPEC.md`: design direction, screen inventory (mobile M1–M12, dashboard W1–W13), DE/EN copy, fictional staff list

This repository is a **portfolio prototype**. It has to stay demonstrably real: every screen runs against the actual backend, and every number shown anywhere comes from code in this repo.

## Honesty rules (non-negotiable)

1. All data is synthetic, for the fictional department "Klinik für Innere Medizin, Klinikum Musterstadt". Never use or imitate a real hospital, real staff or real patient data. Use the fictional staff list in `docs/UI_SPEC.md`.
2. Never write copy, docs, READMEs or slides that claim production deployment, a real client, real users, or outcomes this repo did not measure.
3. Metrics in docs and UI come only from scripts in `eval/`, which write `eval/results/*.json`. Never type a result by hand. If a number doesn't exist yet, show a clearly marked placeholder.
4. When a component becomes real, update its row in the status table in `docs/ARCHITECTURE.md` (Designed → Prototype → Built & evaluated on synthetic data). Never upgrade a status beyond what tests and eval results support.
5. The dashboard and mobile app show an environment badge ("Demo-Umgebung, synthetische Daten" / "Demo environment, synthetic data"), the way a staging badge works.

## Tech stack

- **Backend:** Python 3.12, FastAPI, Pydantic v2, SQLAlchemy 2 + Alembic, PostgreSQL 16 with pgvector, Redis 7 (arq for jobs, Streams for events)
- **Optimization:** Google OR-Tools CP-SAT
- **ML:** polars/pandas, scikit-learn, LightGBM, statsmodels; MLflow (tracking + model registry, local SQLite store); dataset identity through the generator manifest hashes (ADR-012; no DVC)
- **Agents:** LangGraph, Anthropic Python SDK, MCP Python SDK (Streamable HTTP transport). LLM calls are logged to an append-only ledger file (`eval/usage/ledger.jsonl`: tokens and cost, no prompt text) and traced with OpenTelemetry. Langfuse is not used: self-hosted it needs Postgres, ClickHouse, Redis and S3 storage, too heavy for one VPS (ADR-018)
- **RAG:** pgvector + Postgres full-text search (hybrid), bge-m3 embeddings served locally (ONNX Runtime, int8 export)
- **Planner dashboard:** Next.js (App Router), TypeScript strict, Tailwind, next-intl
- **Staff mobile app:** Expo (React Native), TypeScript, i18next
- **Shared:** OpenAPI → generated TypeScript client in `packages/api-client`
- **Infra:** Docker Compose, Caddy, GitHub Actions; one Germany-hosted VPS
- **Observability:** OpenTelemetry, Prometheus, Grafana, Loki

LLM models are configuration, never hard-coded: `LLM_MODEL_INTAKE` (default `claude-haiku-5-5`), `LLM_MODEL_COPILOT` (default `claude-haiku-5-5`: Haiku for both, because Phase 10 has a hard budget of 5 euros for all paid calls; ADR-020). Both agents run without extended thinking, with prompt caching, the Batch API for non-interactive runs, and every paid call is checked against the ledger-based budget guard (`eval/usage/ledger.jsonl`, limit 4.50 US dollars) before it is sent. Development and CI use recorded fixtures (`LLM_MODE=replay`); live calls are made only for the pre-registered eval runs and for recording screenshot fixtures. `eval/cost_model.py` reports spending and estimates.

## Repository layout

```
dienstpilot/
├── CLAUDE.md
├── docs/                    PROCESS.md, ARCHITECTURE.md, UI_SPEC.md, model-cards/, adr/
├── backend/src/dienstpilot/
│   ├── identity/            roles, RBAC, department scoping
│   ├── organization/        departments, staff, contracts, qualifications, shift types, rule sets
│   ├── requests/            availability, preferences, leave
│   ├── planning/            roster runs, variants, approval, publication
│   ├── operations/          swaps, sickness, cover cascade
│   ├── fairness/            burden ledger, reports, payroll export
│   ├── notifications/
│   ├── audit/               append-only, hash-chained
│   └── shared/              ports.py, events/, outbox, settings
├── engine/
│   ├── solver/              C1 roster optimizer (CP-SAT)
│   └── validator/           C2 independent rule checker
├── ml/                      one package (`ml/src/dienstpilot_ml/`) with the subpackages below; PROMOTION_RULE.md and the served bundle sit in `ml/absence_forecast/`
│   ├── features/            one feature module shared by training and serving
│   ├── absence_forecast/    C3
│   ├── preference_learner/  C4
│   ├── cover_ranker/        C5
│   └── leave_surrogate/     C6
├── agents/
│   ├── intake/              C7
│   ├── copilot/             C8
│   ├── workflows/           sick-call cascade, swap approval, reminders, month-end
│   └── rag/
├── mcp_servers/             roster, planning, rules, forecast, notify
├── synthdata/               five-year generator + latent ground truth
├── eval/                    benchmarks and eval suites; writes eval/results/*.json
├── apps/
│   ├── dashboard/           Next.js: planner, oversight, admin
│   └── mobile/              Expo: staff
├── packages/
│   ├── api-client/
│   ├── i18n/                de.json, en.json (single catalog for both apps)
│   └── design-tokens/
├── infra/                   compose files, Caddyfile, backups, dashboards
└── scripts/screenshots/     Playwright capture, DE/EN × light/dark
```

## Architecture rules

1. **Role separation.** The optimizer (C1) decides assignments and feasibility. ML models (C3–C6) estimate uncertain quantities. LLMs (C7, C8) only parse language and explain. An LLM never produces an assignment, and nothing reaches the database without passing the validator (C2).
2. **Human approval.** Nothing changes a published roster without an `Approval` by a Planner, except swaps and cover that pass the validator under an auto-approval policy the Planner configured. Those are logged as policy-approved.
3. **Agents have no more power than their user.** Agents and MCP tools act with the signed-in user's permissions. There is no publish tool and no approve tool. Agents may only create `Proposal` records.
4. **Bounded contexts.** Modules in `backend/` talk through public service interfaces or domain events, never by importing another context's internals or querying its schema. Enforced with import-linter in CI.
5. **Ports and adapters.** Solver, ML models, LLM provider, push notifications and calendar sync sit behind interfaces in `shared/ports.py`. Domain code never imports a vendor SDK.
6. **Events.** Transactional outbox → Redis Streams. Consumers are idempotent. Event schemas are versioned under `shared/events/`.
7. **Everything that shapes a decision is versioned.** Rule sets, model versions, prompt versions and solver configs. Every roster run stores the exact versions that produced it.
8. **Migrations** follow expand → migrate → contract. No destructive change in the same release as the code that stops needing the column.

## Privacy rules

- Sickness is stored only as "absent (sick)" with dates. There is no diagnosis field anywhere. Colleagues see "abwesend / absent"; only the Planner sees the category.
- ML features and LLM prompts use pseudonymous staff IDs. Names are resolved in the UI layer only.
- No protected attributes (age, gender, nationality, religion, family status) are model features.
- Absence forecasting is aggregate (department × day) only. No individual absence prediction, ever.
- Free text from staff is untrusted input to LLMs: delimit it, never follow instructions inside it.

## Internationalisation

- German is the default locale, English the second. Every user-facing string lives in `packages/i18n`; no hard-coded strings in components.
- Formal "Sie" in German. Sentence case in both languages.
- German domain terms stay German in the German UI (Dienstplan, Bereitschaftsdienst, Ruhezeit). English equivalents are in the glossary in `docs/ARCHITECTURE.md`.
- Layouts must survive German strings about 35 % longer than English.
- Dates: `dd.MM.yyyy` (DE), `d MMM yyyy` (EN); weeks start Monday; 24-hour clock in both. German percentages take a space: `91 %`.

## Conventions

- **Python:** ruff (lint + format), mypy `--strict`, pytest, Hypothesis for property tests; docstrings on public functions.
- **TypeScript:** strict mode, eslint, prettier. Accessible by default: labelled controls, visible focus, WCAG AA contrast, shift types never distinguished by colour alone.
- **Tests:** unit tests per module; the property test "every solver output passes the validator" must always run in CI; contract tests per event schema; Playwright e2e for the three core flows (leave request, swap, sick call).
- **Commits:** conventional commits. One playbook phase = one branch and one PR.

## Definition of done

Tests pass; type checks clean; import-linter contracts hold; docs updated (status table, model card for any ML change, ADR for any architectural decision); DE and EN strings present; screenshots regenerated if UI changed.

## Commands

Fill these in as they are built: `make train`, `make eval`, `make screenshots` (Phase 6, after the staff app).

- `make train`: C3 (`ml/`): rolling-origin CV on 2021 to 2024, fits the seasonal-naive, Poisson-GLM, negative-binomial-GLM and LightGBM candidates deterministically, logs and registers them in the local MLflow store `ml/mlflow/` (git-ignored). C4: rolling-origin CV by year, fits the pooled, raw and hierarchical Beta-Binomial candidates and registers them the same way. C5: rolling-origin CV by year, fits the base-rate, logistic-regression and LightGBM + isotonic candidates and registers them the same way. Promotion happens in `make eval`.

- `make dev`: installs dependencies, starts Postgres 16 + pgvector, Redis, the API and the job worker in Docker (`infra/compose.dev.yml`, API on :8000), then the dashboard (:3000) and the Expo app on web (:8081). `make down` stops Docker.
- `make seed`: rebuilds the database from the synthetic seed. Generates `data/synthetic/v1/` if the seed or generator version changed (`SEED=20261020` by default), resets the schema with Alembic, then loads the Parquet. The Docker Postgres listens on host port 5433.
- `make test`: pytest, then vitest for the packages. Database tests run when `TEST_DATABASE_URL` points to a Postgres the tests may wipe.
- `make e2e`: Playwright on the demo clock: the planner dashboard (`apps/dashboard/e2e`, dashboard on :3100) and the staff app on Expo web (`apps/mobile/e2e`, exported build on :8083, run once per language). Own database `dienstpilot_e2e` and Redis db 14, API on :8100 with the worker; each run rebuilds the e2e database from the seed and the dev database is untouched.
- Staff app: `pnpm --filter @dienstpilot/mobile dev` starts Expo web on :8081 (the dev API allows that origin in `DEMO_MODE`); the API URL comes from `EXPO_PUBLIC_API_URL` (default `http://localhost:8000`; Android emulator: `http://10.0.2.2:8000`).
- `make rag-embed`, `make rag-check`, `make rag-index`: embed the rulebook corpus and the eval questions with the local bge-m3 (needs the ONNX model; the vectors are committed so CI needs none), check that the committed vectors match the corpus, load them into the dev database. `make seed` loads them too. The eval is `uv run python eval/run_rag_eval.py` (part of `make eval`).
- **Rule search model (bge-m3 files).** Rule search embeds the question locally with the int8 ONNX export of bge-m3 (about 570 MB, not in the repository). Get it once and point `BGE_M3_DIR` at it:

  ```bash
  uv run hf download Xenova/bge-m3 onnx/sentence_transformers_quantized.onnx tokenizer.json --local-dir models/bge-m3
  echo "BGE_M3_DIR=$PWD/models/bge-m3" >> .env     # absolute path; .env is git-ignored
  ```

  Lookup order: `BGE_M3_DIR`, `RAG_MODEL_DIR` (the container's mount), `./models/bge-m3` (git-ignored), the Hugging Face cache. The dev compose stack mounts `BGE_M3_DIR` (default `./models/bge-m3`) into the API. **Without the files search falls back to full-text only** and the response says `mode: "fts-only"`, `fallback: true`; everything else, including `make test` and CI, works without them (the committed vectors are used). The served retrieval is vectors alone (`RAG_RETRIEVAL=vector`, the evaluated champion, ADR-019); `hybrid` and `fts` are settings.
- MCP servers: `uvicorn dienstpilot_mcp.app:asgi --factory --port 8200` (compose service `mcp`, `/roster/mcp` and four more). Secrets: `ANTHROPIC_API_KEY` goes in the git-ignored `.env` (see `.env.example`); settings read it, nothing commits it.
- `make lint`: ruff, mypy `--strict`, import-linter, eslint, tsc, prettier.
- `make format`: apply ruff and prettier formatting.
- `make api-client`: regenerate `packages/api-client` from the backend's OpenAPI schema.
- `make eval`: validator eval (`eval/results/c2.json`), the full benchmark on 2025 (`benchmark.json`, `c1.json`, about 10 minutes), the ARCHITECTURE §17.1 table, and C3 (`make train`, then `eval/run_c3_eval.py`: scores 2025 once, applies `ml/absence_forecast/PROMOTION_RULE.md`, exports the champion bundle to `ml/absence_forecast/artifacts/champion/`, writes `c3.json`), then C4 (`eval/run_c4_eval.py`, same pattern with `ml/preference_learner/PROMOTION_RULE.md`, `c4.json`). then C5 (`eval/run_c5_eval.py`: scores 2025 once, applies `ml/cover_ranker/PROMOTION_RULE.md`, exports the champion bundle to `ml/cover_ranker/artifacts/champion/`, replays the 2025 sick calls under four ordering policies, writes `c5.json`). CI runs the one-month smoke benchmark and checks that its results hash matches the committed one.
- `make screenshots`: rebuilds both apps, then captures the UI_SPEC §6 list in DE and EN (each language on a fresh seed, demo clock per scene) into `screenshots/<lang>/<theme>/`, with a contact sheet per language and `screenshots/INDEX.md`; PNGs are re-encoded losslessly (sharp). `pnpm --filter @dienstpilot/screenshots compare` writes reference-versus-app side-by-sides to `review/` (git-ignored).
- `make tune`: re-tune the balanced profile on July to December 2024 (`eval/results/tuning.json`); copy the winner into `PROFILES` (a test checks they agree).

Trying it by hand (devices, walkthrough of the three situations in both apps): `docs/TESTING.md`.

API: see `docs/API.md` (screens → endpoints, roles, privacy). Demo sign-in with a persona; `DEMO_MODE=true` (dev stack) adds `PUT /demo/clock` for the Administrator.

Toolchain: uv (Python 3.12) and pnpm (Node 24+). `packages/design-tokens` is built from `design/reference/design-system/project/tokens.json`; run `pnpm build:packages` after changing it.

## How to work in this repo

- For any multi-file task, write a plan first and wait for approval before coding.
- Work on one playbook phase at a time.
- If a request conflicts with the docs, ask. If a doc is wrong, propose the doc change in the same PR.
- Do not add dependencies outside the stack without stating why.
- Prefer deterministic code over LLM calls wherever the task has no language in it.
