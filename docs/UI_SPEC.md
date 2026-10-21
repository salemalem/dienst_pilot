# DienstPilot: UI specification

Two surfaces: the **staff app** (mobile, used one-handed between patients) and the **planner dashboard** (web, used at a desk). German is the default language, English the second; every screen must exist in both. Process context is in `PROCESS.md`, data and logic in `ARCHITECTURE.md`.

## 1. Demo world

- **Department:** Klinik für Innere Medizin, Klinikum Musterstadt (fictional)
- **Demo date:** Tuesday, 20 October 2026. The request window for December 2026 is open (six weeks ahead); November 2026 is the live, published month.
- **Environment badge** on every screen: "Demo-Umgebung, synthetische Daten" / "Demo environment, synthetic data".

### Fictional staff (use consistently)

| Name | Role in clinic | App role | Used in |
|---|---|---|---|
| Prof. Dr. Claudia Hoffmann | Chefärztin | Planner (day-to-day roster delegated to Dr. Brandt) | approval context |
| Katrin Vogel | Personalabteilung (HR) | Oversight | W12 reports |
| Dr. Thomas Brandt | Oberarzt, responsible for the roster | Planner | dashboard persona |
| Dr. Lea Lorenz | Fachärztin | Staff+ | accepts swap (Situation B) |
| Dr. Aylin Kaya | Assistenzärztin | Staff | leave request (Situation A); main mobile persona |
| Dr. Rohan Mehta | Assistenzarzt | Staff | offers swap (Situation B) |
| Dr. Jonas Weber | Assistenzarzt | Staff | reports sick (Situation C) |
| Dr. Sofía Alvarez | Assistenzärztin | Staff | accepts cover (Situation C) |
| Dr. Marek Nowak, Dr. Hannah Schulz, Dr. Yusuf Demir, Dr. Ines Becker, Dr. Felix Wagner, Dr. Mira Okafor, Dr. Paul Richter, Dr. Anna Lehmann, Dr. Tobias Klein, Dr. Elif Arslan | mixed | Staff / Staff+ | fill the roster grid |

Remaining staff up to about 28 come from the synthetic generator.

## 2. Design direction

**Subject.** The real artefact in this world is the printed Dienstplan pinned to the wall of the doctors' room: a dense grid of names and days with shift letters, marked up by hand. DienstPilot is that grid made alive and calm. The **roster grid** is the one memorable element; everything around it stays quiet and disciplined.

**Starting palette** (a proposal for Claude Design to refine; avoid cream-and-terracotta, black-with-neon and generic SaaS card kits).

> Superseded: the final tokens live in `design/reference/design-system/project/tokens.json`, built into `packages/design-tokens`. They add Rufbereitschaft as a sixth shift type (`shift-ruf`) and move Bereitschaft from teal `#2F8A7A` to green `#2A7F5B` for colour-blind separation from grey leave. The table below is kept as the starting point only.

| Token | Hex | Use |
|---|---|---|
| ink | `#1C2B36` | text, primary icons |
| paper | `#F6F8F9` | app background (light) |
| action | `#1F5FD1` | primary buttons, links, focus |
| frueh | `#E3A72F` | Frühdienst (sunrise amber) |
| spaet | `#8B5FBF` | Spätdienst (dusk violet) |
| nacht | `#24345E` | Nachtdienst (deep navy) |
| bereitschaft | `#2F8A7A` | Bereitschaftsdienst |
| frei | `#9AA5B1` | leave / free (with hatching) |
| alert | `#B3261E` | rule violations only |

**Shift-type system.** Every shift is shown as a colour **and** a letter so it works without colour: F (Früh / Early, E in EN), S (Spät / Late, L), N (Nacht / Night, N), B (Bereitschaft / On-call, O), R (Rufbereitschaft / On-call from home, H), U (Urlaub / Leave, V for vacation). Letters switch with the language.

**Type.** One legible family. Atkinson Hyperlegible Next is a strong starting point because legibility for tired eyes at 03:00 is the point; use tabular figures for hours and times. Claude Design may propose an alternative with a stated reason.

**Dark mode** is a first-class theme, automatically on between 20:00 and 07:00 on mobile, for night shifts.

**Principles.**
- Status before detail: the first line of every screen answers "what do I need to know or do now?"
- Every AI output is visibly a suggestion, with a "Warum? / Why?" affordance that shows the reasoning.
- Buttons name what happens ("Freigeben und veröffentlichen" / "Approve and publish"), and the confirmation uses the same verb ("Veröffentlicht" / "Published").
- Errors say what's wrong and how to fix it, never apologize.
- Mobile: primary actions in the thumb zone; nothing needs two hands.

## 3. Staff app (mobile)

| ID | Screen | Purpose and content | Key copy (DE / EN) |
|---|---|---|---|
| M1 | Anmeldung / Sign in | Hospital SSO, language switch | "Mit Klinik-Konto anmelden" / "Sign in with hospital account" |
| M2 | Heute / Today | Next shift card (time, ward, colleagues on shift); open tasks: December request window, incoming cover request; quick actions: Krank melden, Dienst tauschen | "Ihr nächster Dienst" / "Your next shift"; "Wünsche für Dezember abgeben, noch 6 Tage" / "Submit your wishes for December, 6 days left" |
| M3 | Mein Dienstplan / My roster | Month view with shift letters, list view below; sync-to-calendar toggle | "Mit Kalender synchronisieren" / "Sync to calendar" |
| M4 | Wünsche / Wishes (request window) | Tap days to mark "kann nicht" / "möchte arbeiten"; star up to two as important; free-text box parsed by C7 with a confirmation preview; C4 suggestions as dismissible chips | "Lieber Nächte als Wochenenden" example; "Wir haben verstanden:" / "Here's what we understood:"; "Als wichtig markieren (max. 2)" / "Mark as important (max. 2)" |
| M5 | Urlaub beantragen / Request leave | Situation A: Dr. Kaya selects 14–27 July; instant C6 hint, then the C1 check. Default state: coverable. Conditional state, only when the solver finds a trade-off: the trade-off with two buttons. Staff never see colleagues' names here | Default: "Abdeckbar. Zwei Kolleg:innen haben überschneidende Tage beantragt; die Besetzung bleibt gesichert, ohne Überstunden." / "Coverable. Two colleagues have requested overlapping days; staffing stays covered without overtime."; button "Urlaub beantragen" / "Request leave". Only with a trade-off: "Abdeckbar, wenn Sie im Juni ein zusätzliches Wochenende übernehmen" / "Coverable if you take one extra weekend in June"; buttons "Mit Tausch beantragen" / "Request with trade", "Ohne Tausch beantragen" / "Request without trade" |
| M6 | Dienst tauschen / Swap a shift | Situation B: Dr. Mehta offers his Saturday early shift (21.11.) as an exchange; the offer is shown only to colleagues who can exchange with him (count shown, not names) | "Tausch anbieten" / "Offer exchange"; "Angebot geht an {n} Kolleg:innen, die mit Ihnen tauschen dürfen" / "Offer goes to {n} colleagues who can exchange with you". When a giveaway would drop below contract hours: "Allein abgeben geht nicht: Sie lägen unter Ihren Vertragsstunden. Bieten Sie einen Tausch an." / "You can't give this shift away alone: you'd fall below your contract hours. Offer an exchange instead." |
| M7 | Krank melden / Report sick | Situation C: one tap, date range, no diagnosis field; confirmation states that cover is being organized | "Sie sind ab heute als abwesend eingetragen. Wir suchen eine Vertretung für Ihren Frühdienst. Gute Besserung." / "You're marked absent from today. We're finding cover for your early shift. Get well soon." |
| M8 | Vertretungsanfrage / Cover request | Situation C from Dr. Alvarez's side: shift details, countdown, hours impact, accept/decline | "Können Sie heute den Frühdienst übernehmen? 07:30–16:00, Station 4B" / "Can you take today's early shift?"; "Antwort bis 06:57" / "Reply by 06:57"; "Übernehmen" / "Take shift", "Ablehnen" / "Decline" |
| M9 | Fairness-Bilanz / Fairness balance | Own nights, weekends, holidays this year vs department average; simple dot-on-a-line per category | "Sie liegen bei Nachtdiensten 2 unter dem Durchschnitt" / "You're 2 nights below the department average" |
| M10 | Stunden / Hours | Contract hours, worked, overtime, rest-period compliance for the month | "Überstunden diesen Monat" / "Overtime this month" |
| M11 | Mitteilungen / Notifications | Roster published, swap confirmed, leave decided (with reason) | "Urlaub genehmigt" / "Leave approved" |
| M12 | Einstellungen / Settings | Language, theme, notifications, calendar sync, preference suggestions on/off | "Wunschvorschläge anzeigen" / "Show preference suggestions" |

### 3.1 How the coded staff app resolves the open points

- **Navigation.** Four tabs in the thumb zone: Heute (M2), Dienstplan (M3), Mitteilungen (M11), Einstellungen (M12). The other screens open from quick actions and links and have a back button; every screen has its own URL (ADR-011).
- **M5.** The default state is the honest one: the instant C6 hint (a stand-in estimate, labelled as such) and then C1's answer, "Abdeckbar" with the number of overlapping colleagues and no names. "Mit Tausch beantragen" / "Ohne Tausch beantragen" appear only when the solver returns `coverable_with_trade_off`.
- **M6.** The offer is an exchange: the audience is a count, "Allein abgeben geht nicht" appears when the API says the offerer would fall below the contract-hours band, and incoming offers show the exchange options the validator accepts.
- **M8.** The countdown is the API's `seconds_left` (the demo clock), read again every 15 seconds; "Antwort bis" is the offer's deadline. The station is not shown because the API has none.
- **M9.** One sentence per category with the person's own figure against the department average ("Sie liegen bei Nachtdiensten 2 unter dem Durchschnitt"), a dot on a line, no colleague named or ranked.
- **Theme.** Dark from 20:00 to 07:00 by the demo clock, with "Automatisch / Hell / Dunkel" in M12.
- **Demo menu.** On M1 and in M12: Kaya (default), Weber (M7), Alvarez (M8), Mehta and Lorenz (M6).

## 4. Planner dashboard (web)

Persona: Dr. Thomas Brandt. Layout: left navigation, main canvas, collapsible copilot panel (C8) on the right.

| ID | Screen | Purpose and content | Key copy (DE / EN) |
|---|---|---|---|
| W1 | Übersicht / Overview | Request-window progress for December; open escalations; coverage health for the next 14 days with C3 absence band; recent auto-approved swaps | "Heute braucht nichts Ihre Entscheidung" / "Nothing needs your decision today" (empty state) |
| W2 | Wunschphase / Request window | Progress bar, list of who has and hasn't responded, remind button, close-window action | "21 von 28 haben geantwortet" / "21 of 28 have responded"; "Erinnerung senden" / "Send reminder" |
| W3 | Varianten / Variants | A/B/C side by side: plain-language summary, metrics (wishes, burden spread, overtime), recommendation with one-sentence reason | "Variante A: 91 % der Wünsche erfüllt, Nachtdienste gleichmäßig verteilt, 12 Überstunden" / "Variant A: 91% of wishes granted, nights evenly balanced, 12 hours overtime" (illustrative; real values come from the backend) |
| W4 | Dienstplan-Editor / Roster editor | Grid of physicians × days with shift letters; drag to change; instant C2 messages; gap suggestions | "Ruhezeit von 11 Stunden nicht eingehalten (Dr. Lorenz, 14.→15.12.)" / "11-hour rest period not met (Dr. Lorenz, 14→15 Dec)"; "Lücke am 23.12., Spätdienst. Vorschlag: Dr. Mehta" / "Gap on 23 Dec, late shift. Suggestion: Dr. Mehta" |
| W5 | Freigabe / Approval | Confirmation dialog with summary of what staff will see | "Freigeben und veröffentlichen" / "Approve and publish"; toast "Dezember veröffentlicht" / "December published" |
| W6 | Anfragen / Requests inbox | Leave requests with computed impact (coverage, who covers, overtime, leave taken vs colleagues); escalated swaps; copilot proposals | "Genehmigen" / "Approve", "Ablehnen mit Begründung" / "Decline with reason" |
| W7 | Ausfälle / Absences live | Active cover cascades as timelines (asked, declined, timed out, accepted); escalations with ranked options and consequences | "Lücke geschlossen: Dr. Alvarez übernimmt" / "Gap closed: Dr. Alvarez is covering" |
| W8 | Fairness und Compliance | Burden distribution per person, nights/weekends/holidays, rest compliance, overtime trend | "Verteilung Wochenenddienste 2026" / "Weekend duty distribution 2026" |
| W9 | Copilot panel | Chat with citations to rule sources, what-if results, "Vorschlag erstellen" / "Create proposal"; never a publish button | "Warum hat Dr. Weber im Dezember zwei Wochenenden?" as sample question |
| W10 | Protokoll / Audit trail | Filterable event log: who requested, what was proposed, who approved, when; chain-verified indicator | "Protokoll vollständig und unverändert" / "Log complete and unaltered" |
| W11 | Regeln und Stammdaten / Rules and master data | Admin: shift types, demand templates, qualifications, contracts, versioned rule sets | "Neue Regelversion ab 01.01.2027" / "New rule version from 1 Jan 2027" |
| W12 | Aufsicht / Oversight | Read-only view for Klinikleitung and Betriebsrat: compliance, overtime, cost, fairness statistics, audit export | "Nur Lesezugriff" / "Read-only access" |
| W13 | KI-Transparenz / AI transparency | One card per component C1–C8: what it does, kind (optimization / ML / LLM), version, last trained, key eval metric from `eval/results`, link to model card, and "Kann den Dienstplan ändern: Nein" / "Can change the roster: No" | This screen is the portfolio's "how it works" shot |


### 4.1 How the coded dashboard resolves the open points

- **Navigation.** Groups are "Planung Dezember 2026" (the month comes from the API), "Laufender Betrieb", "Auswertung" and "System" (W11). W7 is called "Ausfälle live / Absences live", as in the design reference.
- **W3 and W5.** A variant card never carries a publish action (the design system forbids one on an AI surface). Each card opens the draft in W4; the Planner's approval (W5) is the dialog behind "Freigeben und veröffentlichen" in W4. It needs the request window closed: a run while the window is open is a **trial run**, labelled on the cards and in the banner.
- **W4.** A drag moves a shift to a colleague on the same day (reassignment; keyboard: Space picks up, arrows choose the person, Space drops, Enter opens the cell). Gap suggestions come from the API for published months only; a draft shows its gaps in the coverage row and as rule messages.
- **W8 and W12 for Oversight.** Fairness is only anonymous statistics (no names on W8). Hours per person (payroll, working-time records) are on W12.
- **W10.** The chain indicator says that the hash chain arrives in Phase 9 until `chain_verified` is true; it never shows a tick it cannot back.
- **W13.** Cards are grouped by kind. Metrics come from `eval/results` through the API (C1, C2); the other components show a marked placeholder, and no model card exists yet.

## 5. Shift types (use these exact times)

| Dienstart | Shift type | DE | EN | Start | End | Break | Net working time |
|---|---|---|---|---|---|---|---|
| Frühdienst | Early shift | F | E | 07:30 | 16:00 | 30 min | 8 h |
| Spätdienst | Late shift | S | L | 13:30 | 22:00 | 30 min | 8 h |
| Nachtdienst | Night shift | N | N | 21:30 | 08:00 (+1 day) | 45 min | 9.75 h |
| Bereitschaftsdienst | On-call duty (in-house) | B | O | 08:00 | 08:00 (+1 day) | — | 24 h for rest-period and maximum-hours checks; pay credit set by the configurable "Anrechnung" rule |
| Rufbereitschaft | On-call from home (Oberärzt:innen) | R | H | 16:00 | 07:30 (+1 day) | — | Only time actually called in |
| Urlaub | Leave | U | V | all day | all day | — | 8 h per working day (credited, not working time) |

Numbers are formatted per locale in the UI (9,75 h in German, 9.75 h in English).

## 6. Screenshot list for the portfolio

Capture each in DE and EN, light theme; capture M2, M8 and W1 additionally in dark theme.

1. M2 Today (Dr. Kaya)
2. M5 Leave request (Situation A)
3. M6 Exchange offer (Situation B)
4. M7 → M8 Sick report and cover request (Situation C)
5. M9 Fairness balance
6. W1 Overview
7. W3 Variant comparison
8. W4 Roster editor with a rule message visible
9. W7 Live cover cascade
10. W9 Copilot answering with a rule citation
11. W13 AI transparency
12. W10 Audit trail
