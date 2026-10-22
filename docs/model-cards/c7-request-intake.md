# Model card: C7 Request Intake Agent (Wunsch-Assistent)

Status: built; evaluated on synthetic utterances against a pre-registered rule (results below, generated from `eval/results/c7.json`). Nothing here was measured on real staff or real requests.

## Intended use

Turn a physician's free text or dictation about the next roster month (German or English) into a typed preference set that the **person confirms** before anything is saved (screen M4, "Wir haben verstanden"). It proposes; it never writes to the roster, and the person's confirmation is the only path to a saved entry. If it is unsure it asks exactly one clarifying question.

The preference set has the same entries as the screen: hard **unavailable** days (explicit inability: "kann ich nicht", "I can't"), soft **avoid_shift_days** (a day and one shift type the person would rather not work: "lieber keinen Nachtdienst am 14.12.", "I'd rather not do a late shift on the 20th"), general shift leanings, and a weekend flag. A soft dislike is never a hard block; turning one into the other is a hard error in the rule.

## Out-of-scope uses

- Reasons, illnesses or any personal background: there is no field for them, the prompt says to ignore them, and a deterministic filter replaces a clarifying question that touches health. Nothing of the sort is stored or asked.
- Anything that changes a roster, approves, publishes or sends.
- Judging people. The text is read for dates and shifts only.

## Model and settings (fixed in the rule before any call)

`claude-haiku-5-5`, no extended thinking, no sampling parameters, `max_tokens` 400, prompts far below 100,000 tokens, the system prompt and the tool definition cached, the Batch API for the non-interactive evaluation. The user's text is placed between delimiters whose code is a hash of the text itself, so text cannot forge its own end; the system prompt says that everything inside is data. Output is a forced tool call with a closed JSON Schema, checked again in code (dates inside the roster month, known shift types).

Privacy: only the text, the month and the language are sent. No names, ids, absence categories or reasons; a test builds the request for all 200 evaluation utterances and for the endpoint and inspects them for staff names and forbidden fields.

## Data

200 synthetic utterances (100 German, 100 English) rendered from structured specs, so the labels are exact (`eval/c7_utterances.json`, generator `eval/c7_utterances.py`). 60 are dev (the prompt may be developed against them), 140 are test (scored once after the prompt was frozen). Categories: explicit inability, ranges and lists, soft dislikes with a shift, both in one sentence (including ten date-for-date pairs of the same day asked for hard and soft), general leanings, ambiguous and vague texts, health reasons, typos and dictation style, and instructions aimed at the assistant. The utterances are generated, so they are cleaner and more regular than real speech.

## Rule and procedure

`agents/intake/PROMOTION_RULE.md` was committed before the first call: seven checks on the 140 test utterances (whole-set exact match at least 10 points above the stand-in with the paired bootstrap interval excluding zero; at most one soft-turned-hard date and fewer than the stand-in; no health text; no followed injection; a clarifying question on at least 80 % of the ambiguous and at most 10 % of the other utterances; latency p95 at most 5 s; within budget). The prompt was frozen (`agents/intake/frozen.json`) before the one test run. If any check fails the stand-in stays and the model is not switched.

## Results

<!-- c7:start -->
The pre-registered run has not been made yet.
<!-- c7:end -->

## Limitations

- Synthetic, template-based utterances; real speech will be messier, so the numbers are not a forecast of real accuracy.
- Dated wishes to work ("am 20.12. würde ich gern arbeiten") are not a field of the set and are not extracted.
- One roster month and one department; German and English only.
- Latency was measured from one machine over the public internet.
