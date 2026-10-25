# Try it yourself: run and walk through DienstPilot

All data is synthetic (fictional Klinik für Innere Medizin, Klinikum Musterstadt). The demo date is **Tuesday 20 October 2026, 06:00**.

## 1. Start everything (about 5 minutes)

You need Docker, `uv`, Node 24+ and `pnpm`.

```bash
make dev        # Postgres, Redis, API (:8000), worker, dashboard (:3000), staff app (:8081)
make seed       # reset the data to the clean demo state (run again any time to start over)
```

| What | URL | Who it is for |
|---|---|---|
| Staff app (phone UI, web) | http://localhost:8081 | doctors |
| Planner dashboard | http://localhost:3000 | Dr. Brandt (Planner), Katrin Vogel (Oversight), IT admin |
| API reference | http://localhost:8000/docs | developers |

Tip: open the staff app in a desktop browser and switch dev tools to a phone size (about 390 px wide).

## 2. Run it on other devices

| Where | How |
|---|---|
| **Same computer, phone-sized** | Browser dev tools, device toolbar, 390 × 844. |
| **iOS Simulator** | `pnpm --filter @dienstpilot/mobile start`, press `i`. The API at `localhost:8000` works as is. |
| **Android emulator** | `EXPO_PUBLIC_API_URL=http://10.0.2.2:8000 pnpm --filter @dienstpilot/mobile start`, press `a`. |
| **Your phone (Expo Go)** | Phone and computer on the same Wi-Fi. `EXPO_PUBLIC_API_URL=http://<your-computer-IP>:8000 pnpm --filter @dienstpilot/mobile start`, scan the QR code. |
| **Phone browser** | Open `http://<your-computer-IP>:8081`. The API must allow that origin: start it with `CORS_ORIGINS=http://<your-computer-IP>:8081` (dev stack only, `DEMO_MODE`). |

Not yet tried by the author: the native (Expo Go, simulator) routes. The web routes are covered by automated tests.

## 3. Who is who

**Staff app** (sign-in screen: "Mit Klinik-Konto anmelden" = Dr. Kaya; "Demo-Menü öffnen" or *Einstellungen* switches person):

| Person | Use for |
|---|---|
| Dr. Aylin Kaya (default) | wishes, leave (Situation A) |
| Dr. Rohan Mehta | offers a swap (B) |
| Dr. Lea Lorenz | takes the swap (B) |
| Dr. Jonas Weber | reports sick (C) |
| Dr. Sofía Alvarez | covers the shift (C) |

**Dashboard** (top right, "Demo-Person"): Dr. Brandt (Planner, default), Katrin Vogel (Oversight, read-only), IT-Administration (rules, **demo clock**).

**Language / theme:** DE | EN switch on both. The staff app is dark from 20:00 to 07:00 *by the demo clock*; *Einstellungen* has Automatisch / Hell / Dunkel.

**Demo clock:** dashboard as IT-Administration → *Regeln und Stammdaten* → "Demo-Uhr": set date and time, "Uhr setzen"; "Auf Ausgangswert zurücksetzen" returns to 20.10.2026 06:00.

## 4. Walkthrough: the three situations (both systems)

### A. Leave request (14–27 July 2027)

1. **Staff app, Kaya:** *Heute* → "Urlaub beantragen". Tap the month arrow 9 times (July 2027), tap **14**, then **27**.
2. See the instant hint (box labelled "C6 · Gebaut"; its wording depends on the served model and it is only an estimate), then the optimizer's answer: **"Abdeckbar. Zwei Kolleg:innen …"**. If the estimate and the optimizer differ, the optimizer's answer stays and one line says so. No names, no trade-off (it only appears when the solver offers one).
3. Tap "Urlaub beantragen".
4. **Dashboard, Brandt:** *Anfragen*, "Urlaubsantrag, Dr. Aylin Kaya". Check the impact, tap "Genehmigen".
5. **Staff app, Kaya:** *Mitteilungen* shows "Urlaub genehmigt".

### B. Shift swap (Saturday 21.11.)

1. **Staff app, Mehta:** *Heute* → "Dienst tauschen" → pick **Sa 21.11. Frühdienst**.
2. Read: "Angebot geht an n Kolleg:innen …" and "Allein abgeben geht nicht …". Tap "Tausch anbieten".
3. Switch to **Lorenz** → "Dienst tauschen" → under "Angebote an Sie" tap **"Übernehmen und Fr 27.11. Frühdienst abgeben"**.
4. Result: **"Bestätigt"**. Both rosters show "Geändert" (*Dienstplan*).
5. **Dashboard, Brandt:** *Übersicht* → "Letzte Änderungen": the swap, "Automatisch freigegeben". *Anfragen* has no swap waiting.

### C. Sick call at 06:40

1. **Dashboard, IT-Administration:** set the demo clock to **20.10.2026 06:40**.
2. **Staff app, Weber:** *Heute* → "Krank melden" → "Krank melden". No diagnosis field. Read the warm confirmation.
3. Set the demo clock to **06:43**.
4. **Staff app, Alvarez:** *Heute* shows "Vertretungsanfrage" → open it. See the shift, "Antwort bis …", the countdown (**12:00**) and the hours effect. Tap **"Übernehmen"**: "Übernommen".
5. **Dashboard, Brandt:** *Ausfälle live*: **"Lücke geschlossen: Dr. Sofía Alvarez übernimmt, 06:43"**.
6. Reset the demo clock when done.

## 5. Walkthrough: the Planner's month (dashboard only)

1. **Brandt → Wunschphase:** "Erinnerung senden", then "Wunschphase schließen".
2. **Varianten:** "Varianten berechnen" (a few seconds). Three variants, one recommended; each checked again by the validator.
3. "Als Entwurf öffnen" on the recommended one (**Dienstplan-Editor**).
4. **Break a rule:** drag a late shift (S) onto a colleague's day so the next morning's early shift (F) follows within 11 hours. A red message names the rule and the fix. "Rückgängig" undoes it. Keyboard: arrow keys, Space picks up and drops.
5. "Freigeben und veröffentlichen" → confirm. Toast: "Dezember 2026 veröffentlicht".
6. *Protokoll* lists who did what; *KI-Transparenz* shows which components are built (C1 to C6), which is partly built (C8: what-ifs and drafting by the agent, the rest by the stand-in) and which is a stand-in (C7).
7. **Vogel** (Oversight): *Aufsicht* is read-only; *Fairness und Compliance* shows no names.

## 5b. Walkthrough: timers, the audit chain and the month end

1. **Brandt → Protokoll:** the indicator says "Protokoll vollständig und unverändert" with the time of the last check. "Jetzt prüfen" runs the verifier again.
2. **Timers follow the demo clock.** As IT-Administration, report nothing yet: first do Situation C up to Weber's sick report, but do **not** answer as Alvarez. Move the demo clock to **06:56**: Alvarez's 15 minutes are over, the next colleague has the request (*Ausfälle live* shows the timeline). Move it to **09:00**: everybody in the list was asked in turn, the cascade waits for Brandt (*Eskalation*). Nobody was asked twice.
3. **Reminders and the nightly check.** Move the clock to **25.10.2026 09:00**. Colleagues who have not answered the December window find "Erinnerung: Die Wunschphase …" in *Mitteilungen* (Staff app); *Protokoll* shows "Erinnerung gesendet" by "System". The check at 02:00 on the way ran too.
4. **Month end.** Move the clock to **02.11.2026**. **Vogel → Aufsicht → Monatsabschluss**: October is prepared, the payroll export is locked. **Brandt** confirms with "Monat bestätigen und abschließen"; the export is released.
5. **Tamper, then catch it** (developer check, with `make dev` running):

```bash
docker compose -f infra/compose.dev.yml exec postgres psql -U dienstpilot -d dienstpilot -c "UPDATE audit.event SET actor_label = 'Someone else' WHERE seq = 10 AND chain_key = (SELECT chain_key FROM audit.chain_head WHERE chain_key <> 'system' LIMIT 1)"
```

   Then **Protokoll → Jetzt prüfen**: the indicator turns into "Protokoll verändert: Prüfung fehlgeschlagen ab Eintrag 10". `make seed` restores the clean state.

## 5c. The rulebook and the MCP servers (developer check)

```bash
# 1. Sign in as the Planner and search the rulebook (German or English questions)
TOKEN=$(curl -s -X POST localhost:8000/auth/demo-login -H 'content-type: application/json' -d '{"persona":"brandt"}' | python3 -c 'import sys,json;print(json.load(sys.stdin)["access_token"])')
curl -s "localhost:8000/rules/search?q=Wie%20lange%20muss%20die%20Ruhezeit%20sein" -H "authorization: Bearer $TOKEN" | python3 -m json.tool | head -30
```

Every passage has a `citation` ("Arbeitszeitgesetz (ArbZG) § 5 Abs. 1 (Stand 2024-12-31)"); synthetic documents say so in theirs. A question with no source ("Wie hoch ist der Urlaubsanspruch?") answers `found: false`. Without the bge-m3 model on the machine (`BGE_M3_DIR` in `.env`, see `.env.example`) the answer says `"mode": "fts-only"`.

The MCP servers run as compose service `mcp` on port 8200 (`/roster/mcp`, `/planning/mcp`, `/rules/mcp`, `/forecast/mcp`, `/notify/mcp`, Streamable HTTP). Send the same bearer token; the Planner sees every tool, Oversight (Katrin Vogel) only the read tools, staff get 403. No tool publishes, approves or sends anything; `create_proposal` and `draft_announcement` put a proposal in the Planner's inbox (*Anfragen*) and nothing else.

## 6. Start over, and automated checks

```bash
make seed       # clean demo state (also after you changed data)
make e2e        # the same walkthroughs as automated tests (own database, ports 8100 / 3100 / 8083)
make test       # unit and API tests
make screenshots  # the portfolio screenshots (DE and EN), contact sheets and INDEX.md in screenshots/
```

## 7. If something does not work

| Symptom | Fix |
|---|---|
| Staff app shows an error or "Daten konnten nicht geladen werden" | Is the API up? `curl localhost:8000/health/ready`. Restart with `make dev`. |
| A situation behaves differently from this page | Data was changed earlier: `make seed`, and reset the demo clock. |
| Alvarez has no request | The demo clock must be **06:43** (not before 06:40) and Weber must have reported sick first. |
| Phone cannot reach the API | Same Wi-Fi, correct `EXPO_PUBLIC_API_URL`, firewall allows port 8000. |
| Login suddenly fails after moving the clock | Reload the page: the app signs in again by itself. |

More: `docs/PROCESS.md` (the three situations told as a story), `docs/UI_SPEC.md` (screens), `docs/API.md` (endpoints), `docs/adr/` (decisions).
