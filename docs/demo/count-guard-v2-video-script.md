# Count Guard v2: video script (offline, keyed, owner handover)

## Summary

The film is three paths and an opening in 3:20. Offline is the safe default and `make demo-check` runs it end to end. Keyed is optional and spends credits.

- Path 1, Das: an outpatient. Prescription, strip check, closed visit, and a patient question answered from the record.
- Path 2, Kumar: hernia repair. Dictated orders, admission, theatre, tray check, swab count, paracetamol by voice, discharge, healing photo, doctor answer.
- Path 3, Iyer: low blood pressure. Voice reading flagged, saline orders, set-up video check, a typed reading back above the limit with the flag answered, discharge, medicine photo.

Totals: doctor 58 s, nurse 58 s, patient 58 s, intro, AI at work and close 26 s, film 3:20.

How to check it: run `make demo-check` from `count-guard/`. It makes the media, runs the unit tests, starts its own servers on ports 8200 and 5273 with no model key, walks all 32 beats in a headless browser, and saves one screenshot per beat in `count-guard/demo-shots/`. It takes about 25 seconds (measured: 23 s, twice). The machine needs: Playwright's cached Chromium or `CG_CHROME` pointing at a Chrome, macOS `say`, `ffmpeg`, and Pillow in `.venv`.

Decision for the owner: film offline or keyed (see Owner handover). The script below is the offline one. Section "Keyed variant" lists what changes.

## Before filming

1. Run `make demo-check` once, or run the three generators (`eval/p2/make_media.py`, `eval/p3/make_clips.py`, `eval/p4/make_photos.py`). They write the files named in this script: `kumar-orders.wav`, `kumar-paracetamol.wav`, `kumar-discharge.wav`, `rao-answer.wav`, `iyer-bp.wav`, `iyer-saline.wav`, `strip-paracetamol.png`, `tray-hernia.mp4`, `saline-setup.mp4`, `swabs-closing.mp4`, `wound-day0.png`, `wound-day3.png`, `meds-iyer.png`.
2. Stop the keyed server on port 8100 first (or pass other `CG_API_PORT` and `CG_WEB_PORT` values). Delete the data folder before each take. Start a clean offline server: `rm -rf /tmp/cg-film && make dev MODEL_API_KEY= COUNT_GUARD_DATA=/tmp/cg-film`.
3. Open a new private window. The ward state lives in session storage.
4. Use a 1200-wide window. The patient beats can be filmed in a phone-sized window.
5. Do not press Reset in the first second.
6. The intro beat names port 5273, which is the check's own port. Use your own port when filming.
7. Confirm the dock reads `Synthetic data · models: offline (prepared)` before the first take. If it reads Models: live, stop and restart with the key empty.

## Offline script

Each beat shows its id, start time, role and length. Clicks are numbered. "On screen" lists the text the check waits for. The quote is the narration.

### Intro

#### `intro` · 0:00 · none · 3 s
Clicks: 1) Open http://127.0.0.1:5273/; 2) Role Doctor

On screen: `Synthetic data · models: offline (prepared)` · `Research demo. Not for clinical use.`

> Count Guard is a research demo on a synthetic ward, running with no live model.


#### `ai` · 0:03 · none · 20 s
Clicks: 1) Link "AI at work" in the demo dock; 2) Button "Try sample" in "SAM 3.1"

On screen: `AI at work` · `Muse Voice` · `Muse Spark 1.3` · `SAM 3.1` · `Muse Spark Open` · `Saw 2 of 3 needle holders.` · `1 missing`

> The AI at work page lists the four Muse models on this ward; a sample tray photo shows SAM 3.1 boxes, the counts and a plain explanation.

### Path 1: Mr. Das, outpatient (patient and doctor)

#### `das-rx` · 0:23 · doctor · 5 s
Clicks: 1) Chart A. Das; 2) Button "Use the demo prescription"

On screen: `In clinic` · `Amlodipine`

> Dr. Rao opens Mr. Das, an outpatient, and loads the prescription for his clinic visit.

#### `das-strip` · 0:28 · doctor · 5 s
Clicks: 1) Field "One strip per line: name then strength" <- Amlodipine 10 mg; 2) Button "Check these strips"

On screen: `Strip reads amlodipine 10 mg; prescription says 5 mg.`

> A pharmacy strip is checked against the prescription, and the mismatch is named.

#### `das-close` · 0:33 · doctor · 3 s
Clicks: 1) Button "Close visit"

On screen: `Clinic visit closed` · `The visit is closed. No further steps.`

> Dr. Rao closes the visit, and the record says nothing more is due.

#### `das-ask` · 0:36 · patient · 12 s
Clicks: 1) Role Patient; 2) Pick A. Das; 3) Tab Ask; 4) Textarea in "Ask your record" <- When do I take amlodipine?; 5) Button "Ask the record"

On screen: `Here is what your record says.` · `Amlodipine` · `Rules (no model)`

> Mr. Das asks his own record about his tablet, and the answer comes from the record, with its source named.

#### `das-mycare` · 0:48 · patient · 6 s
Clicks: 1) Tab "My care"

On screen: `Clinic visit closed`

> His My care page shows the closed visit in plain words.


### Path 2: Mr. Kumar, hernia repair (all three roles)

#### `kumar-orders` · 0:54 · doctor · 8 s
Clicks: 1) Role Doctor; 2) Chart R. Kumar; 3) Button "Use the demo prescription"; 4) Button "Dictate orders"; 5) File eval/p2/kumar-orders.wav into "Dictate orders"; 6) Button "Draft orders"

On screen: `Draft from dictation · Rules (no model)` · `Heard by: Prepared demo result` · `Paracetamol`

> Dr. Rao dictates admission orders for Mr. Kumar, and a draft appears with its source named.

#### `kumar-admit` · 1:02 · doctor · 4 s
Clicks: 1) Button "Sign orders"; 2) Button "Admit"

On screen: `Being admitted` · `Nurse acknowledges the new orders from Dr. A. Rao, then completes the admission.`

> Dr. Rao signs the orders and admits him; the screen says which nurse step comes next.

#### `kumar-admission` · 1:06 · nurse · 6 s
Clicks: 1) Role Nurse; 2) Tab "My queue"; 3) Chart R. Kumar; 4) Tick "Wristband on", "Allergies checked", "Baseline observations taken", "Consent on file"; 5) Button "Complete admission"; 6) Button "Acknowledge"

On screen: `On the ward` · `acknowledged the orders at`

> Nurse Meena sees the new orders in her queue, ticks the admission checks and acknowledges the orders.

#### `kumar-theatre` · 1:12 · doctor · 6 s
Clicks: 1) Role Doctor; 2) Select "Procedure" <- hernia-repair; 3) Button "Send to theatre"

On screen: `Swabs: 15` · `In theatre` · `Dr. A. Rao: In theatre with R. Kumar, free about`

> Dr. Rao picks the hernia repair and sends him to theatre; the doctor's status follows.

#### `kumar-chip` · 1:18 · patient · 5 s
Clicks: 1) Role Patient; 2) Pick R. Kumar; 3) Tab Today

On screen: `In theatre with R. Kumar`

> Mr. Kumar's own Today page shows the doctor is in theatre with him.

#### `kumar-free-soon` · check only, not filmed · nurse
Clicks: 1) Role Nurse; 2) Chart R. Kumar; 3) Button "+1 h" in "Demo clock"

On screen: `In theatre with R. Kumar, expected free soon`

> Check only: after the clock moves on one hour, the theatre chip reads expected free soon.

Filming note: `kumar-free-soon` is not in the film. The check moves the clock on one hour here and reads the chip. In the filmed take the +1 h move is skipped (or done off camera and not shown), and `kumar-tray` follows `kumar-chip` directly, so its first two clicks (Role Nurse, Chart R. Kumar) are on camera.

#### `kumar-tray` · 1:23 · nurse · 6 s
Clicks: 1) Role Nurse; 2) Chart R. Kumar; 3) File eval/p3/tray-hernia.mp4 into "Tray check"

On screen: `Flagged: not everything planned was seen. The surgeon decides.` · `Needle holder` · `1 missing` · `Saw 2 of 3 needle holders.`

> Nurse Asha films the tray; the check finds one needle holder missing and flags it for the surgeon.

#### `kumar-count` · 1:29 · nurse · 9 s
Clicks: 1) Button "Surgery began"; 2) Button "Record pack opened" (prefilled 15); 3) File eval/p3/swabs-closing.mp4 into "Swab camera count"; 4) Button "Record closing count" (prefilled 14 by the camera); 5) Field "Closing count (returned)" <- 15; 6) Button "Correct the count"

On screen: `Closing count: 14 of 15 back, 1 unaccounted.` · `Correction recorded.` · `Read 14, saved 15 by Nurse Asha`

> Surgery begins, the pack opens at 15 swabs, the camera counts 14 back, and the count is corrected to 15 when one is found.

#### `kumar-back` · 1:38 · nurse · 4 s
Clicks: 1) Button "Surgery ended"; 2) Button "Back to ward"

On screen: `On the ward` · `Dr. A. Rao: Available`

> Surgery ends and he returns to the ward; Dr. Rao shows as available again.

#### `kumar-paracetamol` · 1:42 · nurse · 7 s
Clicks: 1) Button "Say it: Paracetamol…" on the Paracetamol row; 2) File eval/p2/kumar-paracetamol.wav into that row; 3) Button "Use this"; 4) File eval/p2/strip-paracetamol.png into "Confirm task"; 5) Button "Confirm"

On screen: `Paracetamol 1 g given to bed 4.` · `Heard by: Prepared demo result` · `Photo matches the task` · `by voice`

> Nurse Meena records the paracetamol round by voice, adds the strip photo, and confirms.

#### `kumar-mycare` · 1:49 · patient · 7 s
Clicks: 1) Role Patient; 2) Pick R. Kumar; 3) Tab "My care"

On screen: `, by voice` · `Photo matches the task`

> Mr. Kumar's My care page shows the task as done by voice, with the photo check.

#### `kumar-discharge` · 1:56 · doctor · 8 s
Clicks: 1) Role Doctor; 2) Chart R. Kumar; 3) Button "Wound photo"; 4) Button "Add reference photo" <- eval/p4/wound-day0.png; 5) Button "Dictate discharge"; 6) File eval/p2/kumar-discharge.wav into "Dictate discharge"; 7) Button "Draft discharge"; 8) Button "Sign discharge"

On screen: `Reference` · `15 of 15` · `Heard by: Prepared demo result` · `Being discharged`

> Dr. Rao adds a reference wound photo, dictates the discharge summary, and signs it.

#### `kumar-home` · 2:04 · nurse · 3 s
Clicks: 1) Role Nurse; 2) tick "Discharge card given", "Medicines handed over", "Reminders set"; 3) Button "Complete discharge"

On screen: `Home`

> The nurse completes the discharge checks and he goes home.

#### `kumar-ask` · 2:07 · patient · 12 s
Clicks: 1) Role Patient; 2) Pick R. Kumar; 3) Tab Ask; 4) Textarea in "Ask Dr. Rao" <- Is the swelling normal on day 3?; 5) Button "Send to Dr. Rao"; 6) Text input in "Healing photo" <- Day 3; 7) File input in "Healing photo" <- eval/p4/wound-day3.png

On screen: `Waiting for Dr. Rao` · `The doctor reviews your healing photo.`

> At home Mr. Kumar asks Dr. Rao about his wound and sends a day 3 photo; the page says who is waiting.

#### `kumar-review` · 2:19 · doctor · 9 s
Clicks: 1) Role Doctor; 2) Tab "My patients"; 3) Row "R. Kumar" under "Waiting on you"; 4) In "Ask inbox", the item with the question: file eval/p2/rao-answer.wav into "Your answer"; 5) Button "Send to R. Kumar"; 6) Button "No visit needed"

On screen: `Healing photo` · `Reference` · `Heard by: Prepared demo result` (before Send to R. Kumar) · `by voice · Prepared demo result` · `No visit needed`

> Dr. Rao opens the healing photo beside the reference photo and answers by voice.

#### `kumar-answers` · 2:28 · patient · 6 s
Clicks: 1) Role Patient; 2) Pick R. Kumar; 3) Tab Ask

On screen: `The wound looks as expected for day 3.` · `No visit needed`

> Mr. Kumar sees the doctor's answer and the decision on his Ask page.


### Path 3: Ms. Iyer, low blood pressure and saline (all three roles)

#### `iyer-bp` · 2:34 · nurse · 6 s
Clicks: 1) Role Nurse; 2) Chart S. Iyer; 3) Button "Say it: BP and pulse…" on the BP and pulse row; 4) File eval/p2/iyer-bp.wav into that row; 5) Button "Use this"; 6) Button "Confirm"

On screen: `BP 82 over 54, pulse 112, bed 7.` · `is below the limit of 90`

> Nurse Meena records Ms. Iyer's blood pressure by voice; it falls under the doctor's limit and is flagged.

#### `iyer-orders` · 2:40 · doctor · 7 s
Clicks: 1) Role Doctor; 2) Tab "My patients" (row reads "Observation past its limit"); 3) Chart S. Iyer; 4) Button "Dictate orders"; 5) File eval/p2/iyer-saline.wav into "Dictate orders"; 6) Button "Draft orders"; 7) Button "Sign orders"

On screen: `Draft from dictation` · `Nurse acknowledges the new orders from Dr. A. Rao.`

> Dr. Rao sees the flagged reading in her queue, dictates saline orders, and signs them.

#### `iyer-setup` · 2:47 · nurse · 8 s
Clicks: 1) Role Nurse; 2) Button "Acknowledge"; 3) File eval/p3/saline-setup.mp4 into the input labelled "Add video or photo check"; 4) Button "Begin"

On screen: `Set-up matches the list` · `Saline 1 litre over 2 hours, video check of the set-up running`

> The nurse acknowledges the orders, films the saline set-up, and the check matches the list before she begins.

#### `iyer-end` · 2:55 · nurse · 2 s
Clicks: 1) Button "+1 h" twice; 2) Button "End"

On screen: `finished Saline 1 litre over 2 hours, video check of the set-up at`

> The clock moves two hours and the nurse ends the saline task.

#### `iyer-recheck` · 2:57 · nurse · 5 s
Clicks: 1) Role Nurse; 2) Button "Say it: BP and pulse every 1 h"; 3) Textarea "What was said" in that row <- BP 112 over 70, pulse 84, bed 7.; 4) Button "Use this"; 5) Button "Confirm"; 6) Field "What you did or saw" in the below-the-limit flag <- Reading checked again at the bedside; 7) Button "Answer" in that flag

On screen: `logged BP 112/70, HR 84` · the waiting strip no longer shows `→ Systolic BP 82 is below the limit of 90`

> Her next reading is typed in and is back above the limit; the nurse answers the flag and it clears.

#### `iyer-discharge` · 3:02 · doctor · 3 s
Clicks: 1) Role Doctor; 2) Button "Dictate discharge"; 3) Field "Summary" <- Recovered on the ward after saline. BP back above the limit.; 4) Button "Sign discharge"

On screen: `Being discharged`

> Dr. Rao types a short summary and signs the discharge.

#### `iyer-home` · 3:05 · nurse · 2 s
Clicks: 1) Role Nurse; 2) tick "Discharge card given", "Medicines handed over", "Reminders set"; 3) Button "Complete discharge"

On screen: `Home`

> The discharge checks are ticked and she goes home.

#### `iyer-meds` · 3:07 · patient · 10 s
Clicks: 1) Role Patient; 2) Pick S. Iyer; 3) Tab Ask; 4) File input in "Medicines photo" <- eval/p4/meds-iyer.png

On screen: `Ibuprofen` · `Pantoprazole 40 mg:` · `Ibuprofen 400 mg · not prescribed`

> Ms. Iyer photographs her medicines; the page flags one row and names each medicine with its schedule.


### Close

#### `close` · 3:17 · none · 3 s
Clicks: 1) Role Doctor; 2) Tab "My patients"

On screen: `Dr. A. Rao: Available`

> Back on My patients, Dr. Rao shows as available and every step above has a record.

## Keyed variant

Answer first: keyed changes the labels and turns prepared answers into live ones. Every other beat is the same as offline. Beats with no model call are not listed.

Offline labels read `Rules (no model)` and `Prepared demo result`. Keyed labels read `Muse Voice`, `Muse Spark` or `SAM 3.1`, and answers are prose. Live speech can use the mic button, the WAV files, or typing in the box.

| Beat | Model calls and label change |
|---|---|
| `intro` | No model call. Say instead: "Count Guard is a research demo on a synthetic ward, running with live models." The dock reads models: live, not offline, when a key is set. |
| `ai` | Try sample makes live calls with a key: SAM 3.1 runs one image call per tray concept (7). The chip reads live in place of Sample or prepared. |
| `das-ask` | No model call: a medicine question is answered by quoting the prescription row. The label reads Rules (no model) with or without a key. |
| `kumar-orders` | 1 Voice call and 1 Spark text call. Labels read Muse Voice and Muse Spark; Heard by reads Muse Voice. Live speech can be replaced by typing in the box. |
| `kumar-tray` | SAM 3.1 video call (clip seconds, capped at 120 s). The label reads SAM 3.1. Switch: TRAY_LIVE. Run make cost CLIP=<file> for the bill. |
| `kumar-count` | SAM 3.1 video call for the swab camera count. The label reads SAM 3.1. Switch: SWABS_LIVE. |
| `kumar-paracetamol` | 1 Voice call and 1 Spark text call, plus 1 SAM 3.1 image call and 1 Spark vision call for the strip photo. Labels read Muse Voice and Muse Spark; Heard by reads Muse Voice. No switch. |
| `kumar-discharge` | 1 Voice call and 1 Spark text call. Labels read Muse Voice and Muse Spark; Heard by reads Muse Voice. Live speech can be replaced by typing in the box. |
| `kumar-review` | 1 Voice call (hear). Heard by reads Muse Voice. No switch. |
| `iyer-bp` | 1 Voice call and 1 Spark text call. Labels read Muse Voice and Muse Spark. No switch. |
| `iyer-orders` | 1 Voice call and 1 Spark text call. Labels read Muse Voice and Muse Spark. Live speech can be replaced by typing in the box. |
| `iyer-recheck` | 1 Spark text call (typed text, no Voice call). The label reads Muse Spark. No switch. |
| `iyer-setup` | SAM 3.1 video call. The label reads SAM 3.1. Switch: SETUP_LIVE. |
| `iyer-meds` | 1 SAM 3.1 image call (strip regions) and 1 Spark vision call. The label reads Muse Spark. Switch: MEDICINES_LIVE. |

Cost and order:

- The video checks are the costly calls. The cut order (D3) is the saline video first, the medicine photo second.
- Run `make cost CLIP=eval/p3/tray-hernia.mp4` for the SAM bill before a keyed run.
- The owner's `make dev` loads the Meta key, so a keyed run spends credits on every model beat.
- Drawn stand-in clips give poor live SAM results (P3-R24). For a keyed take, set `TRAY_LIVE` and `SETUP_LIVE` to `False` until the real clips exist, and run `make cost CLIP=eval/p3/tray-hernia.mp4` first.

## Owner handover

### The cut switches

| Switch | File | `False` does |
|---|---|---|
| `TRAY_LIVE` | `count-guard/backend/app/journey/video_api.py:22` | Tray check always uses the prepared result. |
| `SWABS_LIVE` | `count-guard/backend/app/journey/video_api.py:23` | Swab camera count always uses the prepared result. |
| `SETUP_LIVE` | `count-guard/backend/app/journey/video_api.py:21` | Set-up check always uses the prepared result. |
| `MEDICINES_LIVE` | `count-guard/backend/app/journey/ask_api.py:30` | Medicine photo always uses the prepared result. |

All four are `True` in the code. With no key they have no effect, because the run is offline. Edit the line and save: uvicorn reloads on save, so no restart is needed.

### Clip and photo names

The prepared results key on the file name stem. Keep these names when you replace a drawn stand-in with real footage:

- `tray-hernia.mp4`: film the tray with one needle holder held back, then film it complete. Film on a desktop, not a phone.
- `swabs-closing.mp4`: film the returned swabs laid out, 14 of them. Film on a desktop, not a phone.
- `saline-setup.mp4`: film the saline set-up showing bag, line, cannula and label. Film on a desktop, not a phone.
- Photos are accepted wherever a video check is offered.
- Offline, a check with several photos follows the first file. Upload the intended one first.
- The prepared results are the JSON files in `count-guard/backend/app/journey/prepared/`, named by file stem (for example `tray-hernia.json`, `saline-setup.json`, `meds-iyer.json`).

### Re-record the boxes (once)

Export `MODEL_API_KEY` in your shell, then run `.venv/bin/python eval/record_fixtures.py --spend` from `count-guard/`. It prints the request count (about 41) and the `make cost` bill for the clips first, and refuses without `--spend`. A fixture whose live counts differ is left alone; the run writes `<stem>.live.json` beside it and exits 2. The run also prints how many regions SAM found per reader concept (`READER_CONCEPTS` in `journey/regions.py`). `swabs-closing` is skipped until its clip exists. Until you run it, the viewer labels results Sample.

### Keyed vs offline

- Offline (the default, and what `make demo-check` runs): no model key, labels read `Rules (no model)` and `Prepared demo result`, no credits spent.
- Keyed: you start the backend with a key and film by hand. Labels change to `Muse Voice`, `Muse Spark` or `SAM 3.1`. See "Keyed variant" for the calls per beat. The run is never keyed.

### Running the check

`make demo-check` from `count-guard/`. Offline only. A refused run (ports 8200 or 5273 in use) keeps the earlier screenshots. To clear a "Port in use" refusal, find the leftover process (`lsof -i :8200 -i :5273`) and stop it, then run again. The check never stops a server it did not start.

### Known limits

- The tray list comes from open incisional hernia counts, while the template title says inguinal. The preview shows the source note (P5-R4).
- The swab total is 15. The count beat shows `14 of 15` first, then the correction to 15.
- No openly licensed tray or saline footage exists. NC-licensed footage is excluded (P3-R1). The media are drawn stand-ins until filmed (D12, P2-R2).
- A photo cannot be attached when a begin-and-end task is begun, except through the set-up check.
- Iyer's card uses the hernia care template (P5-R3).
- The offline bot quotes only the record. Keep the scripted questions.
- The `/journey` old screen still shows raw nudge kinds. It opens by URL only (P5-D1).
- The Guide's Journey card stays (P5-R2).
- One doctor only. The role switcher is a lens, not a sign-in.

## Appendix: where things live

| Item | Location |
|---|---|
| Beat table | `count-guard/frontend/scripts/demo/beats.mjs` |
| Runner | `count-guard/frontend/scripts/demo/run.mjs` |
| Servers (ports 8200, 5273) | `count-guard/frontend/scripts/demo/server.mjs:7` |
| `make dev`, `make cost`, `make demo-check` | `count-guard/Makefile:40`, `:27`, `:44` |
| Data folder variable | `count-guard/backend/app/config.py:84` |
| Switches | `video_api.py:21-22`, `ask_api.py:30` (under `backend/app/journey/`) |
| Where the switches apply | `video_api.py:148`, `:155`; `ask_api.py:174` |
| `/journey` route | `count-guard/frontend/src/App.jsx:189` |
| Media generators | `count-guard/eval/p2/make_media.py`, `eval/p3/make_clips.py`, `eval/p4/make_photos.py` |
| Drift test | `count-guard/frontend/scripts/demo/doc.test.mjs` |
