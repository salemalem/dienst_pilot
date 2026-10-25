# ADR-021: How C8 runs, what leaves the process, and what it may answer

- Status: Accepted
- Date: 2026-10-25
- Phase: 10c (C8 planner copilot)

## Context

C8 reads rosters, rules and what-if results and writes wording. It must act with no more power than the signed-in user, never send a name or a diagnosis to a vendor, never act on text written by a person, and be served only for what its pre-registered gates (`agents/copilot/RELEASE_GATES.md`, committed before the first call) let it.

## Decision

1. **A LangGraph loop over MCP tools, one run per question, as a background job.** `think` (one model call), `act` (the tool calls of that turn, one after the other), repeat, `final_answer`, grounding check. At most 8 turns and 1,200 output tokens per turn. `POST /copilot/ask` queues an arq job and returns 202 with a run id; `GET /copilot/runs/{id}` is polled by W9 (like solver runs, ADR-009). The job calls the MCP servers with the **asking user's own token** (passed as a job argument, never part of the job id), so the API's role checks apply to every tool call; the tool list is whatever the servers list for that role. There is no publish, approve, decide, send or close tool; the tool-name guard from ADR-018 still applies.
2. **Aliases at the boundary.** Staff ids and names become `P1`, `P2`, ... (sorted by id, so a run is reproducible) on the way out and are restored only when the answer is shown. An ambiguous surname becomes a neutral phrase. Before each request the new text is scanned for names, surnames, person ids, persona keys and health words (rulebook passages are exempt from the health-word check, because the rulebook says "Krankmeldung"); a finding stops the run before anything is sent. The dictionary *keys* of tool results are aliased too (the first full run showed ids leaking through `hours_delta`).
3. **Free text is data.** Change reasons, decision reasons and proposal texts reach the agent only through `get_history`, wrapped in delimiters with a code derived from the text; the prompt says they are data and the injection tasks test it. `get_history` is a new read tool over a new Planner-only endpoint.
4. **Numbers must be grounded.** A number or date in an answer must be in the question, in a tool result of the run, or in the result of `calculate` (whose operands must be grounded too); otherwise the labelled fallback (the sources queried, no model text) replaces the answer. The check ignores the sign of a number and treats a day in a list of dates as a date; it is re-run by the scorer on the recorded tool results, so a change to the checker applies to every recorded run alike.
5. **Release per capability.** `agents/copilot/champion.json`, written by `eval/run_c8_eval.py report`, says which capabilities passed their gates. Questions are routed by keywords (not by a model) to the agent only for released capabilities (what-ifs, drafting); lookups and rule questions go to the keyword stand-in, whatever the model could do. If a safety gate fails nothing goes to the agent. Without a key (and not in replay mode) the stand-in answers everything and says so. The C8 card is "partial" when the agent serves some capabilities and the stand-in the rest; W13 counts it separately.
6. **Replay serves recordings of real answers.** In `LLM_MODE=replay` (e2e, screenshots) a question is answered from `agents/fixtures/C8/demo/` (real runs of four demo questions, made with `run_c8_eval.py record`), labelled "Aufzeichnung einer echten Antwort"; a question without a recording goes to the stand-in. Tests run without any key (`ANTHROPIC_API_KEY` is emptied for the test session) after a copilot job in a test once made a paid call from the developer's `.env`.
7. **Thinking is explicitly off for tool loops.** The model thinks by default unless told not to, which showed as empty answers at `max_tokens`; the adapter sends `thinking: disabled` for non-forced calls and nothing for forced ones.
8. **Not evaluated, not served:** variant summaries and the month-end narrative stay as they were (the narrative is a labelled placeholder). They were not among the 50 tasks.

## Consequences

- Two capabilities are live behind a key; two stay stand-ins by the numbers, and the model card says why.
- The worker needs the `mcp` service (`MCP_URL`) and the API key in its environment; the compose file passes both.
- Every new tool that returns free text must be wrapped in the same delimiters; a test of the guard and the committed privacy scan over all recorded runs would catch a leak, not prevent a new kind of one.
