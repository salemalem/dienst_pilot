# ADR-007: Synthetic data is reproducible from a seed; DVC waits for the ML phase

- Status: Accepted; item 5 (DVC) amended by ADR-012: DVC is not introduced, dataset identity comes from the manifest hashes
- Date: 2026-10-20
- Phase: 2 (synthetic data generator)

## Context

The prototype runs entirely on synthetic data (ARCHITECTURE §8.1). The generator must produce the same dataset every time, the backend must load it through the bounded contexts, and training code must never see the latent ground truth. ARCHITECTURE §8 names DVC for dataset versioning.

## Decision

1. **Standalone generator.** `synthdata/` is its own package with no imports from `backend/`, and the backend never imports it (import-linter contracts in both directions). The only interface is the output: Parquet files in `data/synthetic/v1/<context>/<table>.parquet` plus `manifest.json`.
2. **Reproducible from the seed.** Output depends only on the seed and the generator version. The generator uses one named random stream per part of the simulation, UUIDv5 identifiers, fixed column types and sorted rows, and never reads the wall clock. A test asserts byte-identical files for the same seed. The manifest records seed, version, periods, rule-set versions, and a row count and SHA-256 hash per file.
3. **Ground truth apart.** Latent parameters and recorded violations go to `_truth/`. A test fails if any code outside `synthdata/` and `eval/` refers to it.
4. **Loading through the contexts.** Each context (organization, requests, planning, operations) has its own Postgres schema, its own models and a public `seed.load()`. `dienstpilot.seeding` verifies hashes and cross-context references, then replaces the seeded tables in one transaction. There are no foreign keys between schemas; cross-context references are plain UUIDs checked by the loader.
5. **DVC deferred to Phase 8 (ML)** (amended by ADR-012: not introduced in Phase 8a either; the manifest hashes identify the data). `data/` is gitignored. While the dataset can be regenerated in seconds from the seed and its manifest proves which build is present, DVC would add a remote and a second source of truth without versioning anything that is not already reproducible. DVC is introduced when training datasets, feature snapshots and models need to be versioned together with MLflow.

## Consequences

- `make seed` rebuilds the database from nothing: generate if needed, reset the schema with Alembic, load.
- Changing the generator changes the data. Bump `GENERATOR_VERSION`, which makes `make seed` regenerate.
- An evaluation result is tied to the seed and generator version recorded in the manifest, not to a DVC hash. Since Phase 8a, results also record the SHA-256 of every file read (ADR-012).
