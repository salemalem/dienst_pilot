# DienstPilot playbook: from documents to portfolio piece

This is your guide, not Claude Code's. It tells you what to paste where, in what order, and what you can truthfully say at each stage.

## 0. What's in this package

| File | Goes to | Purpose |
|---|---|---|
| `CLAUDE.md` | repo root | Claude Code reads it every session: stack, rules, layout, honesty rules |
| `docs/ARCHITECTURE.md` | repo `docs/` | the technical design, readable by recruiters and engineers |
| `docs/UI_SPEC.md` | repo `docs/` + Claude Design | screens, copy in DE/EN, design direction, fictional staff |
| `docs/PROCESS.md` | repo `docs/` | save your existing process description here, unchanged |
| `PLAYBOOK.md` | keep for yourself | this file |

## 1. Two tracks, and what each lets you say

**Track A, Showcase.** Clickable dashboard and mobile app on synthetic data, plus the architecture doc. Fastest route to screenshots.
What you can say: "I designed DienstPilot with a physician and built a working UI prototype on synthetic data. Here's the architecture."

**Track B, Proof.** Everything in Track A, plus the solver, the four ML models, MCP servers and agents actually built and evaluated on the synthetic five-year dataset.
What you can say: "I built and evaluated it end to end on a synthetic five-year dataset of a fictional department. Here are the benchmark results and model cards."

Recommendation: do Track A first for screenshots, then at least Phases 2 and 3 of Track B (data generator and solver). The solver is the first thing a strong interviewer will dig into, and having it run makes every conversation easier.

## 2. Setup

1. Create a repo `dienstpilot` (private until you're ready).
2. Copy `CLAUDE.md` to the root and `docs/` alongside it. Save your process description as `docs/PROCESS.md`.
3. Create `design/reference/` for exports and screenshots from Claude Design.
4. Commit before the first Claude Code session, so every change after that is a reviewable diff.

## 3. Claude Design: visual direction first

Use Claude Design to settle the look before any code exists. Attach `docs/UI_SPEC.md` and `docs/PROCESS.md` to each prompt.

**Prompt D1: design system**
```
You're designing DienstPilot, AI-assisted duty scheduling for German hospital departments. Attached: the process description and the UI spec. Read section 2 of the UI spec first.

Create the design system on one canvas: colour tokens (start from the palette in the spec, refine it, keep the shift-type colours distinguishable in light and dark), type scale, the shift-type chip (colour + letter, DE and EN letters), buttons, form controls, a roster-grid cell in all its states (assigned, wish granted, wish missed, rule violation, gap, leave), the "suggestion" pattern with a "Warum? / Why?" affordance, and the environment badge.

Before drawing, write a short plan (palette, type, layout principles) and check it against the spec: if any choice reads like a generic SaaS dashboard, change it and say why. The memorable element is the roster grid, modelled on the paper Dienstplan on the wall of a doctors' room. Everything else stays calm.
```

**Prompt D2: mobile screens**
```
Using the design system we just made, design the staff app screens M1–M12 from the UI spec at iPhone size, German first. Persona: Dr. Aylin Kaya. Demo date Tuesday 20 October 2026. Use only the fictional names and copy from the spec.

Then show M2, M5, M7 and M8 in English too, and M2 and M8 in dark theme. Primary actions sit in the thumb zone. Every AI suggestion is visibly a suggestion.
```

**Prompt D3: planner dashboard**
```
Design the planner dashboard screens W1–W13 from the UI spec at 1440 px wide, German first. Persona: Dr. Thomas Brandt. The roster editor (W4) is the hero: a dense grid of about 28 physicians × 31 days of December 2026 with shift letters, one visible rest-period violation message and one gap suggestion. The copilot panel (W9) answers "Warum hat Dr. Weber drei Wochenenden?" with a cited rule source. W13 shows the eight components C1–C8 from the architecture doc as honest cards with "Kann den Dienstplan ändern: Nein".

Then show W3, W4 and W13 in English.
```

Iterate in conversation until you're happy, then put whatever Claude Design lets you export, or screenshots of the canvases, in `design/reference/`. Claude Code will match them.

## 4. Claude Code: one phase per session

How to run each session:
- Start fresh for each phase so the context holds only what that phase needs.
- Paste the phase prompt. Ask for a plan first (or use plan mode) and read it before approving.
- Review the diff, run the tests yourself, commit, then move on.
- When a phase finishes, make sure the status table in `docs/ARCHITECTURE.md` was updated honestly.

### Track A

**Phase 1: scaffold**
```
Read CLAUDE.md, docs/ARCHITECTURE.md and docs/UI_SPEC.md. Plan first; don't write code until I approve the plan.

Scaffold the monorepo exactly as laid out in CLAUDE.md: Docker Compose with Postgres 16 + pgvector and Redis; FastAPI backend with a health endpoint and the bounded-context packages (empty but importable); Next.js dashboard with next-intl (German default, English toggle); Expo app with i18next; packages/i18n with a single de.json/en.json catalog used by both apps; packages/design-tokens built from the tokens in design/reference (or UI_SPEC §2 if none). Add Makefile targets dev, test, lint; GitHub Actions running ruff, mypy, pytest, eslint, tsc; import-linter contracts that forbid cross-context imports.

Done when: `make dev` starts everything, both apps switch DE/EN at runtime, CI is green.
```

**Phase 2: synthetic data generator**
```
Read CLAUDE.md and docs/ARCHITECTURE.md §8.1. Plan first.

Build synthdata/: a seeded generator for the fictional "Klinik für Innere Medizin, Klinikum Musterstadt", January 2021 to December 2025. Include the staff structure, rotations, shift types, demand templates, seasonal absence waves, school-holiday leave peaks, latent per-person preferences and cover willingness, swap behaviour, and historical rosters produced by a simulated manual-planner heuristic with realistic imperfections. Write latent parameters to data/synthetic/v1/_truth/ and make training code unable to import from it. Load everything into Postgres through the domain models and snapshot to Parquet identified by manifest hashes (ADR-007, ADR-012; no DVC). Document every assumption in synthdata/ASSUMPTIONS.md. Use the fictional names from docs/UI_SPEC.md for the visible staff.

Also seed November 2026 as a published roster and an open December 2026 request window matching the demo date in UI_SPEC §1.

Done when: same seed gives identical output, a summary notebook shows the seasonal patterns, tests pass.
```

**Phase 3A: API for the UI (Track A version)**
```
Read CLAUDE.md and docs/UI_SPEC.md. Plan first.

Build the read and write endpoints the screens in UI_SPEC need, backed by the seeded data. Where a component isn't built yet (solver, ML, agents), implement the port with a simple deterministic stand-in (a greedy roster, a seasonal-average forecast, a templated summary) and label it as a stand-in in the code and on the W13 transparency screen. Generate the OpenAPI client into packages/api-client.

Done when: every screen in UI_SPEC can be rendered from real API responses.
```

**Phase 4: planner dashboard**
```
Read CLAUDE.md, docs/UI_SPEC.md §2 and §4, and the references in design/reference/. Plan first.

Build W1–W13 in apps/dashboard on the real API. Match the design references closely. All strings through packages/i18n in DE and EN. The roster editor must call the validator endpoint on every drag and show the message inline. Show the environment badge. Accessible: keyboard navigation in the grid, visible focus, AA contrast, shift letters alongside colour.

Done when: all screens work in both languages and both themes, Playwright smoke tests pass.
```

**Phase 5: staff app**
```
Read CLAUDE.md, docs/UI_SPEC.md §2 and §3, and design/reference/. Plan first.

Build M1–M12 in apps/mobile on the real API, including the three flows: leave request with trade-off (Situation A), swap offer (B), sick report and cover acceptance (C). Automatic dark theme 20:00–07:00 with a manual override.

Done when: the three flows work end to end against the backend in both languages.
```

**Phase 6: screenshots**
```
Write scripts/screenshots/ with Playwright: for every entry in UI_SPEC §5, log in as the right persona, navigate to the state described, and capture DE and EN (plus dark where listed). Render mobile screens via Expo web inside an iPhone-sized frame. Output to screenshots/<lang>/<theme>/<id>.png and a contact sheet.

Done when: `make screenshots` regenerates the full set from a clean seed.
```

### Track B (adds the real intelligence)

**Phase 7: validator and solver (C2, C1)**
```
Read CLAUDE.md and docs/ARCHITECTURE.md §8 and §9 (C1, C2). Plan first.

Write the validator first, test-driven, with Hypothesis property tests. Then build the CP-SAT model with the hard constraints and soft objectives as specified, three weight profiles with a diversity constraint, and infeasibility explanation via assumption literals. Add the property test "every solver output passes the validator" to CI. Write eval/run_benchmark.py comparing the manual-planner baseline with the solver on held-out months; it writes eval/results/benchmark.json and regenerates the table in ARCHITECTURE §17.1. Replace the greedy stand-in from Phase 3A and update W13 and the status table.

Done when: benchmark runs reproducibly and the table is generated, not typed.
```

**Phase 8: ML models (one session per model)**
```
Read CLAUDE.md and docs/ARCHITECTURE.md §9 (C3) and §13. Plan first.

Build ml/absence_forecast: features in ml/features (shared with serving), seasonal-naive and GLM baselines, LightGBM Poisson challenger, intervals via split conformal prediction, rolling-origin temporal CV. Log to MLflow, register the winner under alias "champion" only if it beats the baseline. Write eval/results/c3.json and docs/model-cards/c3-absence-forecaster.md. Serve via the ML inference service behind the port. Replace the stand-in, update W13 and the status table.
```
Repeat with C4 (also check recovery of `_truth` preferences), C5 (calibration plus the replay simulator for time-to-fill and burden Gini) and C6 (generate solver-labelled training data first).

**Phase 9: backend contexts, events, audit, workflows**
```
Read CLAUDE.md and docs/ARCHITECTURE.md §7, §8 and §9.1. Plan first.

Implement the bounded contexts with transactional outbox and Redis Streams, idempotent consumers, versioned event schemas with contract tests, the hash-chained audit log with a nightly verifier, and the four workflows as durable state machines. Playwright e2e tests for the three core situations.
```

**Phase 10: MCP, RAG, agents (C7, C8)**
```
Read CLAUDE.md and docs/ARCHITECTURE.md §9 (C7, C8), §10 and §11. Plan first.

Build the five MCP servers (Streamable HTTP, role-scoped tokens, tool annotations, output schemas). Build the RAG pipeline with paragraph-aware chunking, local bge-m3 embeddings and hybrid retrieval over the rule corpus. Build C7 with schema-validated structured output and C8 as a LangGraph agent using only MCP tools, with the numeric grounding check and no publish tool. Write the eval suites (200 intake utterances, 50 planner tasks, refusal and prompt-injection tests) and wire them into CI for prompt changes. Add eval/cost_model.py from the Postgres usage log (tokens per call; Langfuse is not used, ADR-018). Update W9, W13 and the status table.
```

**Phase 11: case study**
```
Write README.md as a portfolio case study, drawing only from docs/ and eval/results/: the problem, the design with the physician, the architecture diagram, the eight components and why they are separate, results from eval/results (no hand-typed numbers), screenshots, what's next (the pilot). State clearly that all data is synthetic and the department is fictional.
```

## 5. How to talk about it

Match the verbs to the status table. "Designed" until it's built, "built and evaluated on synthetic data" once eval results exist, "piloted" only after a real clinic has used it.

**English (Track B complete):**
> DienstPilot is a hospital duty-scheduling system I designed with a physician. Rostering is a constraint-optimization problem at its core, so the system pairs a CP-SAT optimizer with learned models for the uncertain parts (absence forecasting, cover acceptance, preference learning) and a Claude-based copilot that explains plans and answers rule questions through MCP tools. I built and evaluated it on a synthetic five-year dataset of a fictional internal-medicine department, and the next step is a one-month parallel pilot with a clinic.

**Deutsch (Track B abgeschlossen):**
> DienstPilot ist ein System zur KI-gestützten Dienstplanung im Krankenhaus, das ich gemeinsam mit einer befreundeten Ärztin [bzw. einem befreundeten Arzt] konzipiert habe. Im Kern ist Dienstplanung ein Optimierungsproblem mit harten Regeln. Deshalb kombiniert das System einen CP-SAT-Optimierer mit gelernten Modellen für die unsicheren Teile (Ausfallprognose, Vertretungsbereitschaft, Präferenzen) und einem Claude-basierten Assistenten, der Pläne erklärt und Regelfragen über MCP-Tools beantwortet. Entwickelt und evaluiert habe ich es auf einem synthetischen Fünfjahresdatensatz einer fiktiven internistischen Abteilung; als Nächstes ist ein einmonatiger Parallelbetrieb in einer Klinik geplant.

## 6. Questions to be ready for

| Question | Short answer | Where it's covered |
|---|---|---|
| Why isn't the schedule produced by an ML model? | Legal rules need guarantees, ML gives probabilities. CP-SAT returns a provably valid plan or a proof that none exists; ML handles the uncertain inputs around it. | §3, C1, ADR-001 |
| How do you guarantee no rule is broken? | Two independent implementations (solver constraints and validator), a property test in CI, and a validator gate before every write. | C2 |
| How did you train without real data? | A synthetic generator with known latent parameters, so I can check whether models recover the truth. Real data would come only under a data processing agreement and works-council approval during a pilot. | §8.1, §13 |
| Doesn't the cover ranker punish reliable people? | The ranking policy is fairness-first; P(accept) only orders people within the same burden bucket. The replay simulator measures burden Gini against a naive policy. | C5 |
| What data goes to the LLM provider? | Pseudonymous, minimal context; names re-attached in the UI; no health or reason text. | §15 |
| How would this get past a Betriebsrat? | Co-determination under §87 BetrVG is planned for: Oversight role, transparent logic, no individual performance scoring, template works agreement. | §15 |
| Is it high-risk under the AI Act? | Likely, as AI allocating work in employment. Built for human oversight, logging, documentation and explanation from the start. | §15 |
| How is it loosely coupled? | Enforced context boundaries, events via outbox, ports around every vendor, registry aliases for models, versioned rules. | §12 |
| What would change for 50 hospitals? | Tenant isolation (row-level security or schema per tenant), solver workers scaled out, contexts extracted where load demands it. | §7, §12 |
