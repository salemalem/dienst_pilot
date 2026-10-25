# Ten-minute demo script

For an interview or a walkthrough with an engineer or a clinician. Everything runs on synthetic data; say so in the first sentence. The screens and steps are the ones in [TESTING.md](TESTING.md); this page is the order, the timing and what to say.

## Before you start (two minutes, not part of the ten)

```bash
make dev && make seed        # clean demo state: Tuesday 20 October 2026, 06:00
```

- Two browser windows side by side: the **planner dashboard** (http://localhost:3000, DE or EN) and the **staff app** at phone width (http://localhost:8081, about 390 px).
- Dashboard person: **Dr. Thomas Brandt** (Planner). Staff app person: **Dr. Aylin Kaya** (the default). Keep **Katrin Vogel** (Oversight) and **IT-Administration** (the demo clock) in the person menu.
- Optional: with no API key, set `LLM_MODE=replay` for the API and worker (the end-to-end tests do) so the copilot shows its recorded real what-if answer; without it the stand-ins answer and say so on screen.
- Demo clock: dashboard as IT-Administration, *Regeln und Stammdaten*, "Demo-Uhr". "Auf Ausgangswert zurücksetzen" returns to 20.10.2026 06:00.

## Script

| Min | Where | What you do | What you say |
|---|---|---|---|
| 0:00 | Dashboard, *Übersicht* (W1), Brandt | Point at the "Demo-Umgebung, synthetische Daten" badge, then the open decisions. | "This is a prototype for hospital duty rosters, on synthetic data of a fictional department. The idea is that the AI proposes and the responsible physician approves; I'll show where that is enforced rather than just claim it." |
| 1:00 | Staff app, Kaya | **Situation A.** *Heute*, "Urlaub beantragen", 14 to 27 July 2027. | "A junior doctor asks for two weeks off. Before submitting she sees an instant hint, labelled as an estimate, and then the optimizer's real answer: coverable, no overtime. She sees no colleague names." |
| 2:30 | Dashboard, Brandt | *Anfragen*, open the request, show the computed impact, tap "Genehmigen". | "The planner sees the effect already calculated and decides in one tap. The system never decides leave." |
| 3:15 | Staff app, **Mehta** then **Lorenz** | **Situation B.** Mehta offers Saturday 21.11. early shift; Lorenz accepts and gives back Friday 27.11. | "The offer only reaches colleagues who are qualified and legally able to take it. Both rosters are re-checked by an independent validator; everything stays valid, so it is confirmed automatically and the planner gets a notice, not a request. If it had broken a rule it would have gone to the planner with the reason." |
| 4:30 | Dashboard as IT-Administration | Set the demo clock to **20.10.2026 06:40**. | "The clock is a demo clock: timers and deadlines in the system run on it, so I can show a morning in two minutes." |
| 4:45 | Staff app, **Weber** | **Situation C.** "Krank melden". Point at the absence of any diagnosis field. | "One tap, no diagnosis asked or stored. Colleagues see 'absent'; only the planner sees the category." |
| 5:30 | Clock to **06:43**; staff app, **Alvarez** | Open the cover request, show the countdown, tap "Übernehmen". | "The system found who can legally cover, ranked them by who has covered least recently, and asked one person with a 15-minute deadline. Alvarez accepts." |
| 6:30 | Dashboard, Brandt, *Ausfälle live* | Show "Lücke geschlossen". Optional: move the clock to 09:00 on a second sick call to show the escalation (W7b). | "The planner made no phone calls. If nobody answers, or the only option is overtime or a locum, it escalates with ranked options and what each costs. Timers survive a restart; they are rows in the database." |
| 7:15 | Dashboard, *Varianten* then *Dienstplan-Editor* | Open the recommended variant as a draft; drag a late shift so the next early shift follows within 11 hours; show the red message and "Rückgängig". | "The optimizer proposes two or three complete valid variants. When the planner edits by hand, the same rules are enforced and explained in plain words. Nothing is visible to staff until 'Freigeben und veröffentlichen'." |
| 8:30 | Dashboard, *KI-Transparenz* (W13) | Scroll the C1 to C8 cards; stop on C7 and C8. | "Eight components, three kinds of tool. The optimizer decides, ML estimates, language models only read and explain. For every learned model the promotion rule was written before the held-out year was scored, and for the four ML models the simple baseline won, so the baseline is what is served. For the language models: the intake agent failed one pre-registered check, so the stand-in is served; the copilot passed its safety gates and serves what-ifs and drafting, not lookups or rules. This screen shows those numbers from the result files." |
| 9:30 | Copilot panel (W9), optional | Ask the what-if sample question. | "Labelled as AI, with the validator's verdict and the sources it looked at. It can create a proposal in the inbox; there is no publish or approve tool at all." |
| 9:50 | Close | Reset the demo clock. | "What is missing: real sign-on, push notifications, a clinic pilot. The pilot is the real test; the time-saved figure in the process description is a hypothesis until then." |

## Questions you will get

- **Does the AI decide anything?** No. The optimizer proposes, the validator checks, a person approves. Agents have no publish or approve tool and act with the signed-in user's permissions. Swaps and cover are confirmed automatically only under a policy the planner switched on, and only if the validator passes them; the log says "policy-approved".
- **Is any of this real data?** No. A generator simulates five years of a fictional department; results say nothing about real hospitals.
- **Why not just use an LLM to build the roster?** It could not guarantee a single rule and could not explain an infeasible month. See ADR-001.
- **Why is the simple model served?** Because the pre-registered rule said the complex one did not earn it. That is a result, not a failure to try.
- **What did the language models cost?** Cents. The ledger of all paid calls is committed (`eval/usage/ledger.jsonl`), with a hard budget.
- **What would you do next?** The list in the README.
