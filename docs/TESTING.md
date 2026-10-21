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
2. See the instant hint (pencil box, labelled "C6 · Platzhalter"), then the optimizer's answer: **"Abdeckbar. Zwei Kolleg:innen …"**. No names, no trade-off (it only appears when the solver offers one).
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
6. *Protokoll* lists who did what; *KI-Transparenz* shows which components are built (C1, C2) and which are stand-ins (C3–C8).
7. **Vogel** (Oversight): *Aufsicht* is read-only; *Fairness und Compliance* shows no names.

## 6. Start over, and automated checks

```bash
make seed       # clean demo state (also after you changed data)
make e2e        # the same walkthroughs as automated tests (own database, ports 8100 / 3100 / 8083)
make test       # unit and API tests
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
