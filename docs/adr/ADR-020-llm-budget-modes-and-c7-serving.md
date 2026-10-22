# ADR-020: A hard budget for paid calls, three LLM modes, and when C7 serves the model

- Status: Accepted
- Date: 2026-10-23
- Phase: 10b (C7 intake agent)

## Context

Phase 10 has a hard budget of 5 euros for every paid LLM call, in total. The agents must run without a key, CI must never need one, and a component whose pre-registered rule fails must not be served (as C3 to C6).

## Decision

1. **One cheap model for both agents:** `claude-haiku-5-5` (`LLM_MODEL_INTAKE`, `LLM_MODEL_COPILOT`). Prices are copied from Anthropic's pricing page into `eval/pricing.json` with the date: input $0.10, output $0.50, cache write $0.125 (5 min) or $0.20 (1 h), cache read $0.01 per million tokens; Batch halves input and output; prompts over 100,000 tokens cost more, so a prompt that long is refused by the cost function. No extended thinking and no sampling parameters exist in the port. `max_tokens` is as low as the task allows (400 for C7). The system prompt and tool definitions are cached; the Batch API is used for the non-interactive C7 evaluation. The model is written into the pre-registered rule: if C7 (or later C8) fails, the stand-in stays and no other model is tried.
2. **A ledger, not a database table, is the budget's truth.** Every live call appends one line (tokens, cost, run id; never text) to `eval/usage/ledger.jsonl`, which is committed. A table in Postgres would be wiped by `make seed` and `--reset`, and a budget that forgets is no budget; this supersedes the "Postgres usage log" of ADR-018. The guard (`dienstpilot_agents.llm.budget`) refuses a call, or a whole batch, whose worst case (every token uncached, output at `max_tokens`) would take the phase total over **4.50 US dollars**, before it is sent; a test covers a call, a batch and the committed ledger's arithmetic. `make llm-cost` / `eval/cost_model.py` report the totals and estimate the runs before they are made.
3. **Three modes** (`LLM_MODE`): `live` (needs `ANTHROPIC_API_KEY` from the environment or the git-ignored `.env`), `replay` (recorded fixtures only: CI, e2e, screenshots; a request without a recording is an error, never a guess), `off`. `auto` (default) is live with a key and off without one, where the labelled stand-ins answer.
4. **Fixtures are real recordings.** `agents/fixtures/<component>/<request hash>.json` is written only by a live call (it carries the model and SDK that produced it); a test checks that each file is consistent with its own request. Development and debugging use them; live calls are made only for the pre-registered evaluation runs and for recording screenshot fixtures.
5. **C7 serves the model only if its rule says so.** `eval/run_c7_eval.py report` applies `agents/intake/PROMOTION_RULE.md` (written before any call) to the recordings and writes `agents/intake/champion.json`; the registry reads it. Without a promotion, with `LLM_MODE=off`, or without a key (and not in replay mode), the keyword stand-in answers; its note says whether a model was evaluated. A model error on one request falls back to the stand-in for that request, labelled. The test run is once per prompt version and only after the prompt is frozen and committed.
6. **A soft dislike is not a hard block.** The preference set gains `avoid_shift_days` (a date and one shift type, the soft `avoid_shift` entry of Phase 8b) next to the hard `unavailable` dates; the rule counts a soft dislike answered as a hard unavailability as a hard error. M4 applies each kind as its own entry type.
7. **Every AI-generated text is labelled** ("KI-generiert", and "Aufzeichnung einer echten Antwort" in replay), in M4 now and in W9 with C8.

## Consequences

- The ledger file grows by one line per paid call and must be committed with the runs it records.
- Prices can change; `eval/pricing.json` says when it was read.
- At these prices the C7 evaluation costs cents; the guard is there because the budget is hard, not because this phase is expensive.
