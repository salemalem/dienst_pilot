# Synthetic data: assumptions

Everything in `data/synthetic/` is synthetic. It describes the fictional "Klinik für Innere Medizin, Klinikum Musterstadt". No real hospital, staff or patient data was used or imitated. The 17 visible names come from the fictional staff list in `docs/UI_SPEC.md`; everyone else has a generated fictional name.

Every statement below marked **Assumption** is a modelling choice made for this prototype. None of them is a measured fact about any real department, and nothing derived from this dataset says how a real clinic works. Simulation parameters (numbers in `synthdata/src/synthdata/config.py`, written to `_truth/params.json`) are inputs, not findings.

This document lists inputs only. Results computed from the data (rates, counts, benchmark numbers) belong in `eval/results/`, produced by scripts.

## 1. Period and demo state

- **Assumption.** History runs from 1 January 2021 to 31 December 2025, daily. It is the period for training and evaluation.
- **Assumption.** 2026 is the *demo period*, marked as such in `manifest.json`. January to October 2026 are simulated the same way as the history, so "this year" views (fairness balance, hours) have data. Models must not train on it.
- The demo moment is Tuesday, 20 October 2026, 06:00 Europe/Berlin (UI_SPEC §1). No timestamp in the dataset is later than that.
- November 2026 is the last planned month. It was published on Monday 19 October 2026 at 14:00, approved by Dr. Thomas Brandt. It has no in-month changes yet.
- The December 2026 request window is open: 28 recipients, 21 answers. Dr. Aylin Kaya has not answered (her open task on M2).
- **Assumption.** Sickness episodes in the demo period start no later than 18 October 2026, so every cover search is settled before the demo moment. The scripted demo events (the 06:40 sick call, the swap offer, Dr. Kaya's July leave request) are not part of the seed; they are played live (§19). The seed only carries the data they need.

## 2. Calendar

- **Assumption.** Public holidays are the NRW set (including Fronleichnam and Allerheiligen), computed from the Easter date. Musterstadt is fictional; the state is chosen only to fix a holiday list.
- **Assumption.** School holidays follow simple rules and are **not** the real calendar of any state:
  - Easter: the Monday of Holy Week plus two weeks.
  - Summer: six weeks from a Monday in late June to mid-July, rotating by year.
  - Autumn: two weeks from the Monday on or after 11 October.
  - Christmas: 23 December to 6 January.
- Shift times are local Europe/Berlin time. Rest periods are computed on real timestamps, so a night over a daylight-saving change is an hour longer or shorter. Hours credited towards contracts use the nominal net hours.

## 3. Department and staff

- **Assumption.** 28 positions at all times: 1 Chefärztin, 4 Oberärzt:innen, 7 Fachärzt:innen and 16 Assistenzärzt:innen (ARCHITECTURE §8.1). People arrive and leave, but every position is always filled.
- **Assumption.** The 2026 team holds all 17 UI_SPEC names, with these roles:
  - Prof. Dr. Claudia Hoffmann: Chefärztin.
  - Oberärzt:innen: Dr. Thomas Brandt, Dr. Ines Becker, Dr. Paul Richter (since 2022), Dr. Tobias Klein (promoted from Facharzt in April 2023).
  - Fachärzt:innen: Dr. Lea Lorenz (promoted in April 2023), Dr. Hannah Schulz, Dr. Yusuf Demir, Dr. Felix Wagner (since July 2022), Dr. Anna Lehmann (promoted in October 2024).
  - Assistenzärzt:innen: Dr. Aylin Kaya, Dr. Rohan Mehta, Dr. Jonas Weber, Dr. Sofía Alvarez, Dr. Marek Nowak, Dr. Mira Okafor, Dr. Elif Arslan (since April 2026, so still in her first year).
  - The two remaining Facharzt positions and nine resident positions are held by generated people.
- **Assumption.** Residents train for 54 to 72 months. Specialists and seniors stay 6 to 15 years. A leaver is replaced the next day.
- **Assumption.** Contracts are 40 hours a week, except Dr. Schulz (30 h), Dr. Lehmann (32 h) and about one in eight generated people (20, 30 or 32 h).
- **Assumption.** Every resident does one six-month external rotation (Intensivstation, Zentrale Notaufnahme, Gastroenterologie or Kardiologie) in training years 2 to 4. It starts on the first of a month and ends on the last day of a month. During it they are employed but not on the department's roster. Nobody rotates out between September and December 2026, so the whole team is on the demo roster.
- **Assumption.** Chefärztin Hoffmann takes part in the Rufbereitschaft rotation. She works no other shift types.
- Titles: the specs give the German title form for nine people (for example "Oberarzt" for Dr. Brandt, "Assistenzärztin" for Dr. Kaya). Everyone else gets the gender-neutral form ("Fachärzt:in"). No gender is inferred from names, and no gender, age, nationality, religion or family-status field exists.

## 4. Qualifications

- **Assumption.** There are three qualifications, derived from the role history:
  - `nachtdienstfaehig`: cleared for night shifts and in-house on-call duty. Residents get it 12 months after starting; specialists and seniors always have it.
  - `facharzt`: specialist status, from the first Facharzt, Oberarzt or Chefarzt period.
  - `oberarzt`: senior back-up for Rufbereitschaft (Oberärzt:innen and the Chefärztin).

## 5. Shift types

The six shift types use the exact times from UI_SPEC §5: Früh, Spät, Nacht, Bereitschaft, Rufbereitschaft and Urlaub. The codes match the design-token keys; `frei` is leave (Urlaub).

- **Assumption.** Burden weights: Früh 1, Spät 1, Nacht 2, Bereitschaft 3, Rufbereitschaft 1, Urlaub 0.
- **Assumption.** A 24-hour Bereitschaftsdienst is credited with 18 hours towards the contract (the configurable "Anrechnung"). For rest periods and maximum hours it counts as 24 hours.
- **Assumption.** Rufbereitschaft adds no planned hours, because only time actually called in counts as working time, and call-ins are not simulated. It is not working time for rest periods, and a senior may hold it on the same day as a Frühdienst.
- **Assumption.** A leave day is credited with the contract's daily hours (weekly hours ÷ 5) on Monday to Friday days that are not public holidays.

## 6. Who may work which shift

- **Assumption.**

  | Role | Shift types |
  |---|---|
  | Chefärztin | Rufbereitschaft |
  | Oberärzt:innen | Frühdienst, Rufbereitschaft |
  | Fachärzt:innen | Früh-, Spät-, Nacht- and Bereitschaftsdienst |
  | Assistenzärzt:innen | Früh-, Spät-, Nacht- and Bereitschaftsdienst |

## 7. Demand

- **Assumption.** Weekday template (Monday to Friday, not a public holiday):
  - Frühdienst: 9; 8 in school holidays; 10 in December, January and February.
  - Spätdienst: 5; 4 in school holidays.
  - Nachtdienst: 2, all `nachtdienstfaehig`.
  - Rufbereitschaft: 1, `oberarzt`.
- **Assumption.** Weekend and public-holiday template:
  - Frühdienst: 2.
  - Bereitschaftsdienst: 2, all `nachtdienstfaehig`, at least one `facharzt`.
  - Rufbereitschaft: 1, `oberarzt`.
- **Assumption.** Day-shift demand is seasonal: fewer elective admissions in school holidays, more patients in the respiratory season. Nights and on-call duty are not seasonal.
- Demand is a minimum. A roster covers a day when at least the required number of qualified physicians are assigned.

## 8. Rules (rules as data, versioned)

**Assumption.** Rule set `2021-1`, effective 1 January 2021:

| Rule | Value |
|---|---|
| `min_rest_hours` | 11 (as in §5 ArbZG) |
| `max_consecutive_nights` | 4 |
| `max_weekends_per_month` | 2 (a weekend counts if the person has any duty on its Saturday or Sunday) |
| `max_on_call_per_month` (Bereitschaftsdienst) | 4 |
| `max_on_call_home_per_month` (Rufbereitschaft) | 10 |
| `free_day_after_on_call` | yes: no duty on the day a Bereitschaftsdienst ends |
| `contract_hours_band` | 80–110 % of the month's contract hours, counting credited leave |
| `contract_hours_band_min_days` | 5: the band applies only in months with at least five rostered workdays |
| `bereitschaft_credited_hours` | 18 |
| `qualification_mix` | as in section 7 |

**Assumption.** Rule set `2026-1`, effective 1 January 2026, changes one rule: `max_consecutive_nights` goes from 4 to 3, attributed to a fictional 2026 works agreement. Each roster run stores the version it was planned under.

The lower edge of the hours band was 85 % in the Phase 2 plan. It is 80 % because at 85 % the band could not be met in months with little leave, when the department has more contract hours than shifts. The planner also adds extra day shifts (section 10) instead of leaving anyone short. The `contract_hours_band_min_days` rule exists because in a month where someone joins, leaves or returns from rotation near the end, a single shift is already 100–200 % of that month's target.

## 9. Request windows (Wunschphase)

- **Assumption.** One window per roster month. It closes at 23:59 on the Monday at least five weeks before the month and opens 14 days earlier at 08:00. For December 2026 that is 12 to 26 October.
- **Assumption.** The roster is published at 14:00 on the Monday at least 13 days before the month, after the run is created two days earlier. For November 2026 that is 19 October.
- **Assumption.** A window goes to everyone employed when it opens who is on the roster for at least one day of the month. Each person answers with their latent responsiveness (mean 0.86, `response_rate`).
- **Assumption.** An answer has:
  - 0 to 4 days marked "kann nicht" (Poisson, mean 1.6).
  - 1 to 5 "möchte arbeiten" days, drawn from the person's latent shift preferences plus noise. 70 % of them name a shift.
  - Up to two of these marked important.
- "Kann nicht" days are hard unavailability for the planner. Wishes are soft.

## 10. Manual-planner heuristic (historical rosters)

**Assumption.** The rosters from before DienstPilot are produced by a simulated manual planner, not an optimiser. They are the baseline the optimiser (C1) will be compared against.

- **Assumption.** The planner fills each month day by day, hardest slots first: Rufbereitschaft, Bereitschaft, Nacht, Früh, Spät. A slot goes to the eligible person with the lowest score:
  - **Pace:** hours so far against the contract hours accrued so far, with leave counting as its days pass.
  - **Wishes:** a bonus for a wish the planner has read. A wish is read with probability 0.75, an important one with 0.9.
  - **Night blocks:** a bonus for continuing a block.
  - **Weekend bias:** weekends lean on the planner's favourite colleagues (latent `planner_favour`), which makes weekends uneven.
  - **Seniors on days:** seniors take Frühdienst first.
  - **Noise:** a little random noise.
- **Assumption.** The planner never breaks a hard rule on purpose: an ineligible person is never assigned. If nobody is eligible, the slot stays a gap.
- **Assumption.** After the greedy pass the planner reshuffles each day to close gaps. A free colleague takes the gap directly. Failing that, a colleague moves from another shift that day into the gap and a free colleague takes the shift they left (for example from Früh to Spät, with a senior taking the Frühdienst). A change is kept only if nobody involved breaks a rule.
- **Assumption.** Then two steps help anyone below the hours band:
  - **Repair:** move a shift to them from someone above the band, if they hold every qualification the giver holds for that shift.
  - **Top-up:** give them extra Früh- or Spätdienste beyond the minimum demand.
- **Assumption.** The planner tries 12 different random passes per historical month and keeps the one with the fewest gaps. For November 2026 it tries up to 300.
- Consequence: every published roster satisfies every hard rule, including the 80 % hours floor, except coverage on days the heuristic could not fill. Those gaps are recorded in `_truth/published_violations.parquet`.
- **Enforced:**
  - The generator refuses to write any published month that breaks a rule other than coverage, and a November 2026 roster with any violation at all.
  - A separate checker reads the rules, times and qualifications from the output. A test runs it over every published month and requires its coverage gaps to equal the recorded ones.
  - `synthdata/scripts/check_seeds.py` (CI job "seeds") does the same for nine seeds.

## 11. Leave

- **Assumption.** Entitlement is 30 working days a year, pro rata for part-year employment. Each person and year draws one block pattern: (10, 10, 5, 5), (15, 10, 5), (10, 10, 10) or (10, 5, 5, 5, 5) working days.
- **Assumption.** Blocks start on a Monday. With probability equal to a person's holiday-period preference, a block is placed in a school-holiday period of at least ten days; otherwise anywhere in the year. A block never crosses a year boundary or a rotation. The preference is a latent Beta(1.6, 3) value times a department-wide scale (capped at 1), set by the calibration below.
- **Assumption.** A request is submitted 60 to 150 days ahead and decided 1 to 10 days later. The planner approves it unless, on some day, 6 people are already on approved leave, or 2 seniors (Oberärzt:innen and the Chefärztin) are when a senior asks.
- **Assumption.** After a decline the person asks again with the block shifted (one week later, then a week earlier, then two weeks later), up to three times. A follow-up request records the declined request it follows (`previous_request_id`); a request without one is a *first request*.
- **Assumption (parameter, PLACEHOLDER).** `target_first_request_decline_rate` = 0.15: the share of decided first requests the planner declines. This value is a placeholder until it is confirmed with a physician.
  - **Calibration:** the generator searches for the department-wide holiday-clustering scale that brings the overall first-request decline rate closest to the target. The search is a deterministic bisection, and every candidate uses the same random streams.
  - **Recorded:** the scale it uses and the rate it achieves go to `_truth/params.json` under `calibration`.
  - **Reported:** `synthdata/scripts/sanity_report.py` reports the rate per holiday period. Only the overall rate is calibrated; the per-period rates follow from where the holidays cluster.
- Requests submitted after the demo moment do not exist. Requests decided after it are `pending`.
- Only the planner's decision is stored: a reason code and the planner's sentence for a decline. The requester's own reason is never collected (data minimisation, ARCHITECTURE C7).

## 12. Sickness

- **Assumption.** Each person has a daily hazard of starting a sick episode. It is the product of:
  - a base rate (`sick_base_hazard` 0.0075);
  - a personal frailty factor (log-normal, σ 0.3);
  - a seasonal factor.
- **Assumption.** The seasonal factor is a respiratory wave per season: a Gaussian bump peaking between mid-December and late February, 14 to 30 days wide, with an amplitude between 0.8 and 2.4, all varying by year. There is also a smaller autumn bump around early November.
- **Assumption.** The hazard is 1.4 times higher in the three days after a night shift (`post_night_hazard_factor`). This shapes the department-level pattern; ARCHITECTURE C3 forecasts only at department × day level.
- **Assumption.** An episode lasts 1 + Poisson(2.6) days, at most 21. It is reported between 06:00 and 07:30 on its first day. Nobody falls sick while on leave.
- **Assumption.** All of a day's sick reports are drawn first; their cover searches then run in report-time order. Nobody who reports sick that day is asked to cover.
- Sickness is stored as "absent (sick)" with dates and report time only. There is no diagnosis field.

## 13. In-month changes (the manual era)

- **Assumption.** Swaps: each month, each person offers at most one published shift, with probability equal to a latent swap propensity. It is the shift they like least.
  - **Who is asked:** up to eight free colleagues with the right qualifications, in random order. Each accepts with a probability from their latent preference for that shift.
  - **Timing (a simplification):** swaps are offered and settled between publication and the start of the month, within 48 hours of the offer. So every swap comes before the month's own sick reports.
  - **Order of events:** swaps and the cover for sickness reported after publication run in the order they happen, so every change in the data follows the one before it in time.
- **Assumption.** Cover: every shift of a sick person is searched for at report time. The planner asks free, qualified colleagues one by one, up to 6, favourites first. Each accepts with a probability that falls with how often they covered in the last 30 days (latent `cover_willingness`, `cover_load_decay`). If nobody accepts:
  - **Frühdienst, with a senior free that day:** the senior takes it as overtime.
  - **Any other case:** a locum, with probability 0.7; otherwise the shift stays unfilled.
- **Assumption (simulation parameter, not a finding).** In the manual era the planner checks only 85 % of changes against the rules (`manual_rule_check_rate`). A colleague who takes an unchecked shift can break a hard rule (rest period, free day after on-call, weekend limit and so on). Every such breach, and every unfilled shift, is written to `_truth/in_month_breaches.parquet` with its source (`swap` or `cover`). How many breaches the dataset contains follows from this parameter. It says nothing about how often real planners make mistakes.
- The benchmark (Phase 7) reports hard-rule violations in published rosters and in in-month changes separately.

## 14. Ground truth (`data/synthetic/v1/_truth/`)

The folder holds:

- per-person latent parameters (`staff_latent`)
- the season waves (`sickness_wave`)
- the expected new sick episodes per day (`department_sickness_hazard`)
- the violations in published rosters (`published_violations`)
- the in-month breaches (`in_month_breaches`)
- all simulation parameters (`params.json`)

Training and application code must not read it. A test fails if anything in `backend/`, `ml/`, `engine/`, `agents/`, `mcp_servers/`, `apps/` or `packages/` refers to it. Only `eval/` (to check whether models recover the hidden structure) and `synthdata/` may.

## 15. Reproducibility

- The output depends only on the seed (default 20261020) and the generator version. Each part of the simulation has its own named random stream, IDs are UUIDv5 values from stable keys, rows are sorted, every column has a fixed type, and nothing uses the wall clock.
- A test checks that two runs with the same seed produce byte-identical files. `manifest.json` records the seed, the generator version, the periods, the rule-set versions, and the row count and SHA-256 hash of every file.
- Sanity report: `uv run python synthdata/scripts/sanity_report.py` writes `reports/absence_and_leave.png` and `reports/sanity_report.md` into the dataset folder.
- `data/` is not committed. `make seed` regenerates it when the seed or generator version changes. Dataset versioning with DVC starts in the ML phase (ADR-007).

## 16. Known limitations

- **Wards:** wards (for example "Station 4B" in the mockups) are not modelled.
- **Rufbereitschaft call-ins:** not simulated.
- **Sickness and contract hours:** known sickness at planning time blocks a day but is not credited towards contract hours.
- **Christmas leave:** leave blocks are only placed in school-holiday periods of at least ten days, so the Christmas holidays get no holiday-period leave.
- **User accounts:** there are no user accounts or app roles (identity context), and HR staff (Katrin Vogel) are not in the dataset yet.
- **December 2026:** there is no roster for it, and no burden ledger.
- **2027:** only demand (§17) and the two scripted leave requests of §19 exist; there are no staff changes, request windows, other leave or absences in 2027.

## 17. Demand through 2027 (generator 1.2.0)

- **Assumption.** Demand (`organization/shift_demand`) runs to 31 December 2027 with the same templates as §7, so that leave requests for 2027 (M5, for example Dr. Kaya's July leave) can be checked with the optimizer.
- Nothing else changed from 1.1.0: every other table is byte-identical apart from the `generator_version` column of `planning/roster_run`, and the demand rows before 2027 are unchanged (checked when the version was bumped).
- Contracts that run past 2026 keep running; nobody joins or leaves in 2027.

## 18. Leave trade-off (M5, "Mit Tausch beantragen")

The staff app checks a leave request in the background with the optimizer (C1). These are product rules for this prototype; the thresholds are parameters in `backend/src/dienstpilot/app/jobs.py`, not findings.

- **Coverable.** The leave month has a valid roster (every hard rule, checked by C2) with the leave, and covering it does not burden colleagues beyond the thresholds below.
- **Coverable with a trade-off.** The leave month is coverable, **but** covering it pushes colleagues beyond a threshold, **and** one extra weekend duty by the requester in the month before compensates:
  - burden thresholds (comparing the leave month solved with and without this leave, one balanced variant each): the department's overtime rises by more than **8 hours**, or the highest weighted burden among colleagues (nights, weekends and public holidays, including the year so far) rises by more than **2 points**;
  - the month before is not yet published and starts after the current month;
  - the requester's weekends with duty in that month = their weekends in an unconstrained plan + 1, and this stays within the weekend limit and every other hard rule: C1 must find a roster with the commitment and C2 must pass it. Otherwise no trade-off is offered (the outcome stays "coverable").
- **Not coverable.** No valid roster exists for the leave month with the leave; the explanation comes from C1's infeasibility analysis.
- **Not applicable.** The leave spans two months, or the leave month is already published (the Planner arranges cover).
- An approved leave with a trade-off is a binding commitment: when the Planner runs C1 for that earlier month, the requester gets at least that many weekends with duty in every variant.
- **Colleagues' pending requests** in the leave month count as leave in both solves (the cautious reading: they may still be approved).
- **What the tests show.** In the scripted Situation A (§19: 14–27 July 2027, two colleagues' pending requests overlapping, real solver with production settings) and in a two-week January 2027 leave, the leave is coverable without crossing either threshold, so **no trade-off is offered**. How often the trade-off applies has not been measured; one API test drives that branch with a test-only wrapper around the real solver.


## 19. Scripted demo scenarios (generator 1.3.0)

The three situations of `docs/PROCESS.md` §4 are played live with the real engines (C1, C2 and the C5 stand-in) on the demo clock; `backend/tests/api/test_demo_scenarios.py` runs each one end to end. The simulation is unchanged; for the default seed only, `synthdata/src/synthdata/scenarios.py` applies the edits below to its finished output, each with a precondition check. Nothing else in the dataset differs from 1.2.0 apart from the `generator_version` column (checked row by row when the version was bumped).

**Situation A: Dr. Kaya asks for 14–27 July 2027.**
- Seeded: two pending leave requests that overlap her dates. Dr. Carla Franke asks for 12–23 July 2027 (submitted 14 October 2026, 09:12). Dr. Niklas Stein asks for 19–30 July 2027 (submitted 16 October 2026, 18:47).
- Live: Dr. Kaya runs the M5 check. With the definition of §18 and the production solver settings, the result is **coverable, no trade-off**; she submits without a trade and the Planner approves. PROCESS.md and the M5 copy in UI_SPEC tell it this way; the trade-off state appears only when the solver finds one.

**Situation B: Dr. Mehta offers his Saturday early shift as an exchange; Dr. Lorenz takes it.**
- No data is edited. The seeded November 2026 roster has no Saturday night shift (weekend nights are covered by the 24-hour Bereitschaftsdienst), Dr. Mehta has no Saturday Bereitschaftsdienst in November, and December is not planned. Giving any of Dr. Mehta's November shifts away alone puts him below the contract-hours band, so the swap is an exchange.
- Live: Dr. Mehta offers his **Frühdienst on Saturday 21 November 2026**. Dr. Lorenz takes it and gives him her **Frühdienst on Friday 27 November 2026** in return. C2 finds the exchange valid for both, the policy approves it, and the Planner sees it under recent changes (W1), not as a request. The only other exchange C2 accepts for that Saturday is her Spätdienst on Monday 30 November.

**Situation C: Dr. Weber reports sick at 06:40 on Tuesday 20 October 2026.**
- Edited in the published October 2026 roster:
  - Dr. Jonas Weber's approved autumn leave ends on Monday 19 October instead of Friday 23 October.
  - He works the Frühdienst from Tuesday 20 to Friday 23 October, on top of the minimum demand (within the Früh cap), so his hours stay as they were and nobody else loses a shift.
  - Dr. Nadia Kaiser works her Frühdienst of Thursday 22 October on Tuesday 20 October instead (Thursday stays covered through Dr. Weber).
  - Dr. Felix Wagner and Dr. Mira Okafor exchange Spätdienste: Wagner works 20 October, Okafor 27 October.
- Why: without the last two edits, C5 ranks Dr. Kaiser and Dr. Wagner above Dr. Alvarez, because their hours are further below their contracts. With them, Dr. Alvarez is first in the C5 order (fewest covers in the last 90 days, then hours against contract) among the colleagues C2 allows to cover the shift.
- C2 finds no new violation in October or November after these edits. None of the edited assignments is referenced by a swap or a cover search.
- Live: at 06:40 (Frühdienst starts at 07:30) Dr. Weber reports sick. The cover search asks Dr. Alvarez first with a 15-minute deadline. She accepts at 06:43 within her contract hours, the policy approves it, and the Planner sees the closed gap under recent changes (W1).
