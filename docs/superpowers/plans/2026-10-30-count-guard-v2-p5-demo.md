# Count Guard v2 · P5 Demo Run Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** The owner gets a click-by-click script for the 3-minute video (Das clinic only, Kumar operated,
Iyer treated) that gives doctor, nurse and patient equal time. A `make demo-check` command runs the
offline version of that script in a headless browser against its own server and fails on the first beat
whose screen text is wrong. `/play` leaves the menus.

**Architecture:** One beat table, `frontend/scripts/demo/beats.mjs`, is the single source of the script:
id, path, role, seconds, narration, the controls clicked, and the text expected on screen. The video
script doc is written from it. A node test fails when the doc and the table differ. A browser runner
(`run.mjs`) runs one step function per beat (`steps.mjs`). It starts its own offline servers on
8200/5273 with a throwaway data folder (`server.mjs`) and finds a local Chromium (`chrome.mjs`). It
saves one screenshot per beat to a git-ignored folder and exits non-zero with the beat name on the
first failure.

**Tech Stack:** Node 24 ESM scripts, `node:test`; `playwright-core` 1.64.1 (devDependency of
`count-guard/frontend`) driving a Chromium already in the local ms-playwright cache; GNU make;
FastAPI/Vite dev servers via `make dev`; Python generators for stand-in media (Pillow, ffmpeg, macOS `say`).

**Spec:** `docs/superpowers/specs/2026-10-29-count-guard-v2-patient-states-design.md`. Sections: D15 (retire
`/play`, P5 script and automated run), D3 (cut switches), D11 (offline prepared results), D12 (owner's
clips), "Demo script (the three paths)", Goals ("the 3-minute video follows the three patients' paths and
gives doctor, nurse and patient equal time"; "anyone opening a patient knows within 5 s …"), anti-goals.
Ledgers (rulings bind this plan): P1 `.superpowers/sdd/2026-10-29-count-guard-v2-p1-states/progress.md`,
P2 `.superpowers/sdd/2026-10-30-count-guard-v2-p2-voice-photo/progress.md`, P3
`.superpowers/sdd/2026-10-30-count-guard-v2-p3-video/progress.md`, P4
`.superpowers/sdd/2026-10-30-count-guard-v2-p4-ask/progress.md`. Rulings that shape this plan: P2-R1/R15
(own offline servers, never 8100), P2-R4 (media generated, never committed), P3-R1 (no NC footage), P3-R2
(owner clip names), P3-R3 (swab line 14 → 15), P3-R24 and P4-R17 (`TRAY_LIVE`, `SETUP_LIVE`,
`MEDICINES_LIVE`), P4-R1 (import Kumar's demo prescription in clinic), P4-R7 (patient picker), P4-R21
(multi-photo offline follows the first file; the run checks a reference photo beside the healing photo),
P4-R22 (fix wave: plain state words, heard-source label, "expected free soon", nudge labels).

## Global Constraints

- Branch `count-guard-v2`, starting after the P4 fix wave commit (HEAD 9da3acc or later). Commit after each
  task with `git -c user.name=lvnpred -c user.email=lvnpred@gmail.com commit`. Never push. No
  `Co-Authored-By` trailer.
- Keep every file under 500 lines.
- No new string shown to a person, and no narration line in the script, may match
  `\b(give|take|stop|increase|reduce|start|administer|consider)\b` (case-insensitive). Exempt, as the spec
  says: the doctor's dictated words and answers, and the patient's own question text.
- **Never call a live model.** Tests never call one. The runner starts its own servers with
  `make dev MODEL_API_KEY= CG_API_PORT=8200 CG_WEB_PORT=5273 COUNT_GUARD_DATA=<tmp>`. It checks
  `GET http://127.0.0.1:8200/journey/models` → `"live": false` before any click and stops if not. It never
  uses, probes or stops port 8100 (the owner's server) or 5173. No `--spend`, no `SPEND=1`. No WebSearch or
  WebFetch.
- `backend/tests/test_repo_hygiene.py` must keep passing. It flags any tracked line matching
  `(MODEL_API_KEY|BASETEN_API_KEY)=\S`. So no new tracked file under `count-guard/` may write the key name
  directly followed by `=` and a non-space (for example the JS literal of the empty key assignment).
  Build such strings from parts (see Task 2).
- P2-R4: media is never committed. Stand-in media come from `eval/p2/make_media.py`,
  `eval/p3/make_clips.py` and `eval/p4/make_photos.py`; their outputs are git-ignored.
- Synthetic only: `Dr. A. Rao (synthetic)`, `Nurse Meena (synthetic)`, `Nurse Asha (synthetic)`, the three
  seeded patients.
- Tests: `cd count-guard && make test`; `cd count-guard/frontend && node --test 'src/care/*.test.js' && npm run build`;
  and, new in P5, `cd count-guard/frontend && node --test 'scripts/demo/*.test.mjs'`. Re-count the
  baselines at dispatch (P4 ended at 338 backend / 87 node before its fix wave).

## Decisions taken here (the spec leaves them open)

| # | Decision | Why | Cost if wrong |
|---|---|---|---|
| P5-D1 | "`/play`" means the one-click scripted demo: the `/journey` screen's "Play the three-act demo" (`POST /journey/episodes/{id}/play`, `backend/app/journey/api.py:456`). Remove the "Journey" entry from the old `Shell` nav (`frontend/src/App.jsx:148`) and the Older screens list (`App.jsx:165`). Keep the route `App.jsx:200`, the screen, the backend route and `journey/play.py`. The Guide's feature card (`backend/app/site.py:85`) stays: it is a developer map, not a menu. | The v1 spec calls that route "the one-click fallback that writes the whole story". That shortcut competes with walking the three paths. | One more link to remove from `site.py` |
| P5-D2 | The runner lives in `count-guard/frontend/scripts/demo/`. `playwright-core` is pinned exactly at `1.64.1` as a devDependency of `count-guard/frontend`. | ESM resolves `playwright-core` from `frontend/node_modules` with no second `package.json` or install. Every P1–P4 walk used headless `playwright-core`. `eval/p5` would need its own install. | A fresh clone runs `npm install` in frontend (already a `make setup` step) |
| P5-D3 | The browser comes from the local ms-playwright cache (the newest `chromium_headless_shell-*`, else `chromium-*`) or `CG_CHROME`. There is no automatic download. `playwright-core` 1.64.1 expects revision 1248; this machine has 1243, which the walks used. | Downloading a browser is a network side effect that the run should not perform silently. | On a machine with no cache, one manual `npx playwright-core install chromium-headless-shell` |
| P5-D4 | One beat table drives both the run and the doc. A node test fails when any beat id, expected string or media file name in the table is missing from the doc. | The script and its check must not drift. A doc copied by hand asserts nothing. | Every doc edit to a beat also edits `beats.mjs` |
| P5-D5 | The prepared discharge transcript changes from "swab count closed 20 of 20" to "15 of 15" (`backend/app/journey/prepared/kumar-discharge.json:2`). A test ties it to the hernia template's swab total. | P3-R3 made the count 14 → 15. The film shows the 15-swab count and then a summary that says 20. | Regenerate one WAV |
| P5-D6 | The reference photo is a new stand-in, `eval/p4/wound-day0.png`. Dr. Rao adds it on the ward after theatre with "Add reference photo". The review shows it beside `wound-day3.png`. | P4-R21 requires the run to check a reference photo beside the healing photo. No stand-in reference photo exists. | One drawn image |
| P5-D7 | Timing is 3 s intro + 58 s doctor + 58 s nurse + 58 s patient + 3 s close = 180 s. A test keeps each role between 54 and 62 s and the filmed total ≤ 180 s. | This is the spec goal, made checkable. | Re-time beats |
| P5-D8 | Beats marked `film: false` (0 s) are checks only, not filmed. There is one: the theatre chip after "+1 h" reads "expected free soon". | P4-R22 wants the check. Filming a clock skip in the middle of the theatre beat wastes seconds. | None |
| P5-D9 | The run is offline only. The keyed variant is documented per beat (labels that change, model calls made, switch that cuts each), never run. | D11 and P2-R1: agents never spend credits. | The owner checks the keyed variant by eye once |
| P5-D10 | The run never clicks Reset. It uses a fresh data folder and a fresh browser context, so the ward seeds on first load. | P1 Task 8 found that Reset within about 1 s of first load can race the seed (404). | None |
| P5-D11 | Iyer's discharge summary is typed into "Summary" (no prepared Iyer discharge audio exists). Her card uses the only care template, `hernia-repair`. This is listed as a known limit and is not fixed. | Adding a second care template is new scope. Iyer's card is not filmed. | Iyer's My care shows hernia wound care if opened |

## Review Focus

1. **The owner's server is running on 8100 with a key, or another walk server holds 8200/5273.** The run
   uses only 8200/5273. When either port is taken, it stops before starting anything and names the port.
   It never kills a process it did not start. Test in Task 2 (`busyPorts`, `devArgs` never names 8100).
2. **A keyed `.env` is present.** `make dev` loads `../.env`. The empty command-line `MODEL_API_KEY` wins,
   and the run still refuses to click unless `/journey/models` says `live: false`. Test in Task 2
   (`assertOffline` throws on `true`, on a missing field and on a non-object).
3. **The run fails halfway (a wrong text, a 500, a crash, Ctrl-C).** The servers it started are stopped,
   ports 8200/5273 are free afterwards, the failing beat is named, a `-FAIL` screenshot exists, and the exit
   code is 1. Checked in Task 5 by breaking one expected string on purpose, then restoring it.
4. **The doc and the run drift apart.** Someone edits a beat's expected text in one place only.
   `doc.test.mjs` fails, naming the missing string. Test in Task 4.
5. **Media are missing on a fresh clone, or no Chromium is installed.** The run stops before starting
   servers. It names the missing file and the generator that makes it, or prints the browser install
   hint. Tests in Task 2 (`missingMedia`, `pickChrome` returns null on an empty cache).

---

## The beat table (exact values for Task 2 and Task 4)

Abbreviations: **D** doctor, **N** nurse, **P** patient. "Chart X" means: click link "Patients", then
the `.patient-list a` link whose text contains X. "Role R" means: click button R inside `[aria-label="Role"]`.
"Pick X" means: in `select[aria-label="Patient"]`, choose the option whose text starts with X. "Tab T" means:
click link T. "File F into S" means: `setInputFiles` on the `input[type=file]` inside the section
`[aria-label="S"]`, or the input whose label text is S. Media folders are relative to `count-guard/`.
Expected strings were read from source (`file:line` given) unless marked **(confirm)**. A **(confirm)**
string is checked against the screen in the Task 3 dry run. Task 3 corrects the table if the app is right
by the spec, and lists the beat for Task 5 if the app is wrong.

| # | id | path | role | s | Clicks (in order) | Expected on screen (all must appear) |
|---|---|---|---|---|---|---|
| 1 | `intro` | intro | none | 3 | Open `http://127.0.0.1:5273/`; Role Doctor | `Models: offline (prepared results)` (`CareShell.jsx:84`); `Research demo. Not for clinical use.` |
| 2 | `das-rx` | das | D | 5 | Chart A. Das; button "Use the demo prescription" | `In clinic`; `Amlodipine` |
| 3 | `das-strip` | das | D | 5 | Field "One strip per line: name then strength" ← `Amlodipine 10 mg`; button "Check these strips" | `The prescription says Amlodipine 5 mg` (`nudges.py:75`) **(confirm)** |
| 4 | `das-close` | das | D | 3 | Button "Close visit" | `Clinic visit closed`; `The visit is closed. No further steps.` (`states.py:41`) |
| 5 | `das-ask` | das | P | 12 | Role Patient; Pick A. Das; Tab Ask; textarea in `[aria-label="Ask the record"]` ← `When do I take amlodipine?`; button "Ask the record" | `Here is what your record says.`; `Amlodipine`; `Rules (no model)` |
| 6 | `das-mycare` | das | P | 6 | Tab "My care" | `Clinic visit closed`; **absent** regex `\b[a-z]+_[a-z_]+\b\|\(seed\)\|undefined` (no raw state words, P4-R13) |
| 7 | `kumar-orders` | kumar | D | 8 | Role Doctor; Chart R. Kumar; "Use the demo prescription"; File `eval/p2/kumar-orders.wav` into "Dictate orders" | `Draft from dictation · Prepared demo result`; `Paracetamol`; field "Reason for admission" is not empty (asserted in the step, not an `expect` string) |
| 8 | `kumar-admit` | kumar | D | 4 | "Sign orders"; "Admit" | `Being admitted`; `Nurse acknowledges the new orders from Dr. A. Rao (synthetic), then completes the admission.` (`states.py:209-210`) |
| 9 | `kumar-admission` | kumar | N | 6 | Role Nurse; Tab "My queue" (Meena's queue lights up); Chart R. Kumar; tick "Wristband on", "Allergies checked", "Baseline observations taken", "Consent on file"; "Complete admission"; "Acknowledge" | `New orders from Dr. A. Rao` (queue, seen before the chart; `derive.js:116`); `On the ward`; `acknowledged the orders at` |
| 10 | `kumar-theatre` | kumar | D | 6 | Role Doctor; select "Procedure" ← `hernia-repair`; "Send to theatre" | `Swabs: 15` (seen before the send); `In theatre`; `Dr. A. Rao: In theatre with R. Kumar, free about` |
| 11 | `kumar-chip` | kumar | P | 5 | Role Patient; Pick R. Kumar; Tab Today | `In theatre with R. Kumar` |
| 12 | `kumar-free-soon` | kumar | N | 0, `film: false` | Role Nurse; Chart R. Kumar; button "+1 h" in `[aria-label="Demo clock"]` | `In theatre with R. Kumar, expected free soon` (`doctor_status.py`, P4-R22) |
| 13 | `kumar-tray` | kumar | N | 8 | File `eval/p3/tray-hernia.mp4` into "Tray check" | `Flagged: not everything planned was seen. The surgeon decides.` (`video.js:7`); `needle holder`; `2 (missing)`; `Prepared demo result` |
| 14 | `kumar-count` | kumar | N | 10 | "Surgery began"; "Record pack opened" (prefilled 15); "Closing count (returned)" ← `14`; "Record closing count"; "Closing count (returned)" ← `15`; "Correct the count" | `Closing count: 14 of 15 back, 1 unaccounted.` (`nudges.py:157`); `Correction recorded.` |
| 15 | `kumar-back` | kumar | N | 4 | "Surgery ended"; "Back to ward" | `On the ward`; `Dr. A. Rao: Available` |
| 16 | `kumar-paracetamol` | kumar | N | 9 | File `eval/p2/kumar-paracetamol.wav` into "Complete a task by voice"; "Add photo" ← `eval/p2/strip-paracetamol.png`; "Confirm" | `Paracetamol 1 g given to bed 4.` (seen before Confirm); `Photo matches the task` (`drafts.js:5`); `by voice` |
| 17 | `kumar-mycare` | kumar | P | 7 | Role Patient; Pick R. Kumar; Tab "My care" | `, by voice`; `Photo matches the task` |
| 18 | `kumar-discharge` | kumar | D | 8 | Role Doctor; Chart R. Kumar; "Add reference photo" ← `eval/p4/wound-day0.png`; File `eval/p2/kumar-discharge.wav` into "Dictate discharge"; "Sign discharge" | `Reference` (Photos card); `15 of 15` (Summary, seen before Sign); `Being discharged` |
| 19 | `kumar-home` | kumar | N | 3 | Role Nurse; tick "Discharge card given", "Medicines handed over", "Reminders set"; "Complete discharge" | `Home` (state badge) |
| 20 | `kumar-ask` | kumar | P | 12 | Role Patient; Pick R. Kumar; Tab Ask; textarea in "Ask the doctor" ← `Is the swelling normal on day 3?`; "Send to Dr. Rao"; text input in "Healing photo" ← `Day 3`; file input in "Healing photo" ← `eval/p4/wound-day3.png` | `Waiting for Dr. Rao`; `The doctor reviews the healing photo.` (`states.py:218`) |
| 21 | `kumar-review` | kumar | D | 9 | Role Doctor; Tab "My queue"; link "Open →" in the row with `Healing photo to review`; in the `[aria-label="Ask inbox"] [data-line]` item with the question, file `eval/p2/rao-answer.wav` into "Answer by voice"; "Send answer"; "No visit needed" | figcaptions `Healing photo` and `Reference` both in "Ask inbox"; `Heard by: Prepared demo result` (seen before Send); `by voice`; `No visit needed` |
| 22 | `kumar-answers` | kumar | P | 6 | Role Patient; Pick R. Kumar; Tab Ask | `The wound looks as expected for day 3.`; `No visit needed` |
| 23 | `iyer-bp` | iyer | N | 6 | Role Nurse; Chart S. Iyer; File `eval/p2/iyer-bp.wav` into "Complete a task by voice"; "Confirm" | `BP 82 over 54, pulse 112, bed 7.` (seen before Confirm); `is below the limit of 90` (`nudges.py:138`) **(confirm)** |
| 24 | `iyer-orders` | iyer | D | 7 | Role Doctor; Tab "My queue" (row shows `is below the limit of 90`); Chart S. Iyer; File `eval/p2/iyer-saline.wav` into "Dictate orders"; "Sign orders" | `Draft from dictation`; `Nurse acknowledges the new orders from Dr. A. Rao (synthetic).` (`states.py:209`) |
| 25 | `iyer-setup` | iyer | N | 8 | Role Nurse; "Acknowledge"; file input labelled "Add video or photo check" ← `eval/p3/saline-setup.mp4`; "Begin" | `Set-up matches the list` (`video.js:11`); `running` **(confirm)** |
| 26 | `iyer-end` | iyer | N | 2 | "+1 h" twice; "End" | `done` on the saline task **(confirm)** |
| 27 | `iyer-discharge` | iyer | D | 3 | Role Doctor; "Summary" ← `Recovered on the ward after saline. BP back above the limit.`; "Sign discharge" | `Being discharged` |
| 28 | `iyer-home` | iyer | N | 2 | Role Nurse; tick the three discharge boxes; "Complete discharge" | `Home` |
| 29 | `iyer-meds` | iyer | P | 10 | Role Patient; Pick S. Iyer; Tab Ask; file input in "Medicine photo" ← `eval/p4/meds-iyer.png` | `Ibuprofen` (flagged row, `askText.js:28`); `Pantoprazole:` |
| 30 | `close` | close | none | 3 | Role Doctor; Tab "My queue" | `Dr. A. Rao: Available` |

Seconds per role: D 5+5+3+8+4+6+8+9+7+3 = 58; N 6+8+10+4+9+3+6+8+2+2 = 58; P 12+6+5+7+12+6+10 = 58;
intro + close 6. Filmed total 180 s.

Narration (`say`) is one short sentence per filmed beat, in plain English, about what the viewer sees and
who acts next. It must pass the no-advice regex. Example for `kumar-tray`: "Nurse Asha films the tray; the
check finds one needle holder missing and flags it for the surgeon."

Keyed difference per beat (`keyed`) names the model call, the label that changes, and the switch. The rows
with model calls are:

| Beat | Model call | Label | Switch |
|---|---|---|---|
| `das-ask`, `kumar-answers` | none for answers; `das-ask` is 1 Spark text | "Muse Spark" in place of "Rules (no model)"; prose answer | none |
| `kumar-orders`, `iyer-orders`, `kumar-discharge` | 1 Voice + 1 Spark text each | "Muse Spark" / "Muse Voice" | none (live speech can be replaced by "Or type what was said") |
| `kumar-tray` | SAM 3.1 video (clip seconds, capped at 120 s) | "SAM 3.1" | `TRAY_LIVE` (`backend/app/journey/video_api.py:22`) |
| `kumar-paracetamol`, `iyer-bp` | 1 Voice + 1 Spark text; plus 1 Spark vision for the strip photo | "Muse Voice", "Muse Spark" | none |
| `kumar-review` | 1 Voice (hear) | "Heard by: Muse Voice" | none |
| `iyer-setup` | SAM 3.1 video | "SAM 3.1" | `SETUP_LIVE` (`video_api.py:21`) |
| `iyer-meds` | 1 Spark vision | "Muse Spark" | `MEDICINES_LIVE` (`backend/app/journey/ask_api.py:30`) |

Prices are not written in the doc; it points to `make cost CLIP=<file>` for the SAM bill of a clip.

---

### Task 1: Retire `/play` from the menus, and the demo data the script needs

**Files:**
- Create: `count-guard/frontend/src/care/older.js`, `count-guard/frontend/src/care/older.test.js`
- Modify: `count-guard/frontend/src/App.jsx:143-167` (nav and `OLDER` read from `older.js`)
- Modify: `count-guard/backend/app/journey/prepared/kumar-discharge.json:2` ("20 of 20" → "15 of 15")
- Test: `count-guard/backend/tests/test_p5_demo_data.py`
- Modify: `count-guard/eval/p4/make_photos.py` (adds `wound-day0.png`; docstring lists it)

**Interfaces:**
- Produces: `older.js` exports `OLD_NAV: [path, name][]` (old `Shell` nav, without `/journey`),
  `OLDER_SCREENS: [path, name][]` (the Older list, without `/journey`), `RETIRED: ["/journey"]` with a
  comment naming D15 and that the route, screen and `POST /journey/episodes/{id}/play` stay.
- Produces: `eval/p4/wound-day0.png`, generated (git-ignored by `eval/p4/*.png`).

- [ ] **Step 0:** Re-read `App.jsx`, `CareShell.jsx` and `AskInbox.jsx` at HEAD. The P4 fix wave landed after this plan was written. Note any aria-label or button text in the beat table that the wave renamed, and correct the table in Task 2.
- [ ] **Step 1: Write the failing tests.**
  `older.test.js`: `test("no menu entry leads to the retired /play screen")`. It asserts that no path in
  `OLD_NAV` or `OLDER_SCREENS` is in `RETIRED`. It reads `../App.jsx` with `fs` and asserts that the text
  still contains `path="/journey"` (code kept), that it imports `OLD_NAV` and `OLDER_SCREENS` from
  `./care/older`, and that it has no `NavLink to="/journey"`.
  `test_p5_demo_data.py::test_discharge_transcript_count_matches_template`: load
  `sample_data/hernia-repair.json` and sum its swab quantities the way `procedures.tray_plan` does (call
  `tray_plan("hernia-repair")["swab_total"]`). Assert that `f"{total} of {total}"` is in the prepared
  `kumar-discharge.json` transcript.
- [ ] **Step 2:** Run `cd count-guard/frontend && node --test src/care/older.test.js`. Expected: FAIL (module missing). Run `cd count-guard && .venv/bin/pytest -q backend/tests/test_p5_demo_data.py`. Expected: FAIL ("15 of 15" not in "… 20 of 20 …").
- [ ] **Step 3:** Create `older.js` and switch `App.jsx` to map over it. Change the transcript to "15 of 15". Add `wound_photo_day0(out)` to `make_photos.py`: same panel as `wound_photo`, with the dressing drawn fresh (a different line colour, so the two thumbnails differ). `main()` writes `wound-day0.png`.
- [ ] **Step 4:** Run both tests. Expected: PASS. Run `.venv/bin/python eval/p4/make_photos.py && .venv/bin/python eval/p2/make_media.py`. Expected: `eval/p4/wound-day0.png` exists and `eval/p2/kumar-discharge.wav` is newer than the JSON. Run the full suites from Global Constraints. Expected: all pass, and `npm run build` succeeds.
- [ ] **Step 5: Commit** `Count Guard v2 P5: retire /play from the menus; discharge line says 15 of 15; reference wound photo`.

### Task 2: Beat table and the pure helpers of the runner

**Files:**
- Create: `count-guard/frontend/scripts/demo/beats.mjs`, `beats.test.mjs`
- Create: `count-guard/frontend/scripts/demo/chrome.mjs`, `chrome.test.mjs`
- Create: `count-guard/frontend/scripts/demo/server.mjs` (pure part only), `server.test.mjs`

**Interfaces:**
- Produces (`beats.mjs`):
  - `ADVICE: RegExp`: the regex from Global Constraints, flag `i`.
  - `ROLES = ["doctor", "nurse", "patient"]`.
  - `MEDIA: Record<string, string>`: each file → its folder (`"kumar-orders.wav": "eval/p2"`, …, `"wound-day0.png": "eval/p4"`).
  - `GENERATOR: Record<string, string>`: folder → generator script (`"eval/p2": "eval/p2/make_media.py"`, `"eval/p3": "eval/p3/make_clips.py"`, `"eval/p4": "eval/p4/make_photos.py"`).
  - `BEATS: Beat[]`, where `Beat = { id, path: "intro"|"das"|"kumar"|"iyer"|"close", role: "doctor"|"nurse"|"patient"|"none", seconds: number, film: boolean, say: string, clicks: string[], expect: string[], absent?: string, files?: string[], keyed: string }`. The values come from the beat table above.
  - `roleSeconds(beats) -> { doctor, nurse, patient, none }` (filmed beats only); `filmSeconds(beats) -> number`.
  - `missingMedia(root: string, exists: (path) => boolean) -> string`: "" when every `MEDIA` file exists, else `"Missing eval/p4/wound-day0.png. Run: .venv/bin/python eval/p4/make_photos.py (or make demo-check)."` for the first missing file.
- Produces (`chrome.mjs`):
  - `pickChrome(dirNames: string[], platform: "darwin"|"linux", arch: "arm64"|"x64") -> string | null`: the path relative to the cache root of the highest-revision `chromium_headless_shell-<rev>` (`chrome-headless-shell-mac-arm64/chrome-headless-shell`, `…-mac-x64/…`, `chrome-headless-shell-linux64/chrome-headless-shell`). Without one, the highest `chromium-<rev>` (`chrome-mac-arm64/Google Chrome for Testing.app/Contents/MacOS/Google Chrome for Testing`, `chrome-linux64/chrome`). Otherwise null.
  - `cacheRoot(env, home, platform) -> string`: `PLAYWRIGHT_BROWSERS_PATH`, else `~/Library/Caches/ms-playwright` (darwin) or `~/.cache/ms-playwright`.
  - `findChrome(env = process.env) -> string`: returns `env.CG_CHROME` when that file exists. Otherwise it returns the picked path when that file exists. Otherwise it throws `Error(INSTALL_HINT)`.
  - `INSTALL_HINT = "No Chromium found for the demo check. Run: cd count-guard/frontend && npx playwright-core install chromium-headless-shell, or set CG_CHROME to a Chrome binary."`
- Produces (`server.mjs`, pure):
  - `API_PORT = 8200`, `WEB_PORT = 5273`, `OWNER_PORTS = [8100, 5173]`.
  - `NO_KEY = ["MODEL_API_KEY", ""].join("=")`. Write it this way so no tracked line reads key-name, `=`, then a quote (hygiene test).
  - `devArgs(dataDir: string) -> string[]` = `["dev", NO_KEY, "CG_API_PORT=8200", "CG_WEB_PORT=5273", "COUNT_GUARD_DATA=" + dataDir]`.
  - `assertOffline(models: unknown) -> void`: throws `Error("The demo server reports live models. Stopped before any click; nothing was spent.")` unless `models?.live === false`.
  - `busyPorts(free: Record<number, boolean>) -> string`: "" when 8200 and 5273 are both free. Otherwise it returns `"Port 8200 is in use. Stop that server first; demo-check never stops a server it did not start."` (first busy port).

- [ ] **Step 1: Write the failing tests.**
  `beats.test.mjs`:
  - `ids are unique and every beat has a known role and path`.
  - `paths run das, then kumar, then iyer` (intro first, close last).
  - `each role is filmed 54 to 62 s and the film is at most 180 s`: assert `roleSeconds` values in [54, 62] and `filmSeconds(BEATS) <= 180`.
  - `check-only beats are 0 s and not filmed`: `film === false` ⇔ `seconds === 0`.
  - `every filmed beat has narration, at least one click and one expected text`.
  - `narration passes the no-advice regex`: no `say` matches `ADVICE`.
  - `every file a beat uses is in MEDIA`, and `missingMedia` returns the generator hint for a missing file and "" when `exists` is always true.
  `chrome.test.mjs`:
  - `picks the newest headless shell`: `["chromium-1243", "chromium_headless_shell-1200", "chromium_headless_shell-1243", "ffmpeg-1011"]`, darwin arm64 → `"chromium_headless_shell-1243/chrome-headless-shell-mac-arm64/chrome-headless-shell"`.
  - `falls back to full chromium`, and `returns null on an empty cache`.
  - `CG_CHROME wins when the file exists` (use a temp file), and `throws the install hint when nothing exists` (`PLAYWRIGHT_BROWSERS_PATH` pointing at an empty temp dir, `CG_CHROME` unset).
  `server.test.mjs`:
  - `devArgs uses 8200/5273 and the data dir, never the owner's ports`: none of the args contains `8100` or `5173`.
  - `the key is passed empty`: `assert.deepEqual(NO_KEY.split("="), ["MODEL_API_KEY", ""])`.
  - `assertOffline stops on live, missing or junk`: throws for `{live: true}`, `{}`, `null` and `"x"`; passes for `{live: false}`.
  - `busyPorts names the first busy port`: `{8200: false, 5273: true}` gives the 8200 message; all free gives "".
- [ ] **Step 2:** Run `cd count-guard/frontend && node --test 'scripts/demo/*.test.mjs'`. Expected: FAIL (modules missing).
- [ ] **Step 3:** Implement the three modules. Copy the beat table into `BEATS`: ids, roles, seconds, clicks (as short human-readable strings naming each control), expect strings, `absent` for `das-mycare`, `files`, and `say` and `keyed` per the guidance above. Apply any renames found in Task 1 Step 0.
- [ ] **Step 4:** Run the scripts tests and `cd count-guard && make test` (the hygiene test reads the new files). Expected: all PASS.
- [ ] **Step 5: Commit** `Count Guard v2 P5: demo beat table, browser finder and offline server guards`.

### Task 3: The browser run and `make demo-check`

**Files:**
- Modify: `count-guard/frontend/scripts/demo/server.mjs` (adds `portFree`, `startServers`)
- Create: `count-guard/frontend/scripts/demo/steps.mjs`, `steps.test.mjs`, `run.mjs`
- Modify: `count-guard/frontend/package.json` and `package-lock.json` (`npm install -D -E playwright-core@1.64.1`)
- Modify: `count-guard/Makefile` (target `demo-check`, in `.PHONY`)
- Modify: `count-guard/.gitignore` (add `demo-shots/`)

**Interfaces:**
- Consumes: everything Task 2 produces.
- Produces (`server.mjs`):
  - `portFree(port: number) -> Promise<boolean>`: tries a TCP connect to 127.0.0.1. It is free when the connection is refused.
  - `startServers({ dataDir, logPath }) -> Promise<{ stop: () => Promise<void> }>`. Steps:
    1. Call `busyPorts`, and throw on a busy port.
    2. Spawn `make` with `devArgs(dataDir)`, `cwd` `count-guard/`, `detached: true`, stdout and stderr appended to `logPath`, and env `{...process.env, MODEL_API_KEY: ""}`.
    3. Poll `http://127.0.0.1:8200/journey/models` for up to 60 s, then call `assertOffline`.
    4. Poll `http://127.0.0.1:5273/` for up to 60 s.
    `stop()` sends SIGTERM to the process group (`process.kill(-pid)`). It waits up to 10 s for both ports to free, then sends SIGKILL. It is safe to call twice.
- Produces (`steps.mjs`, no `playwright-core` import, so tests can load it):
  - `helpers(page, root) -> H`, where `H` = `{ role(name), chart(who), pick(prefix), tab(name), click(name), fill(label, value), file(scope, relPath), skip(label), text(), waitText(s) }`. These are the selectors named in the beat table. `click` matches the button name exactly and takes the first match. `file` resolves `relPath` against `root` (`count-guard/`). `text()` returns `.app` innerText with whitespace collapsed.
  - `STEPS: Record<beatId, (H) => Promise<void>>`: one function per beat id. Inside a step, a "(seen before X)" expect is asserted with `H.waitText(s)` before clicking X.
  - `waitText(page, s, ms = 10000)` and `waitGone(page, regexSource, ms)`.
- Produces (`run.mjs`): runs with `node scripts/demo/run.mjs` from `count-guard/frontend`. Options `--keep-data` and `--headed`. Env `CG_DEMO_UNTIL=<beat id>` stops cleanly before that beat, prints `DEMO CHECK STOPPED before <id> (not a pass)` and exits 3.

- [ ] **Step 1: Write the failing test.** `steps.test.mjs`: `test("every beat has exactly one step")`. It asserts that `Object.keys(STEPS).sort()` deep-equals `BEATS.map(b => b.id).sort()`.
- [ ] **Step 2:** Run `node --test 'scripts/demo/*.test.mjs'`. Expected: FAIL.
- [ ] **Step 3:** Implement `steps.mjs` and `run.mjs`. `run.mjs` does the following, in this order:
  1. Check `missingMedia`, then `findChrome`. Each failure prints its message and exits 1 before any server starts.
  2. Empty `count-guard/demo-shots/`. Make the data dir with `fs.mkdtempSync(os.tmpdir() + "/cg-demo-")`.
  3. Call `startServers` with `logPath` `demo-shots/server.log`.
  4. Launch Chromium headless, 1200×1600, in a new context. Record console errors, page errors and HTTP responses ≥ 400.
  5. For each beat `n`: run `STEPS[id]`. Then check every `expect` with `waitText` and `absent` with `waitGone`. Fail when any console error, page error or HTTP ≥ 400 response arrived during the beat. Save `demo-shots/NN-id.png` (full page).
  6. On the first failure, save `NN-id-FAIL.png` and print `DEMO CHECK FAILED at beat NN <id> (<role>): <reason>` plus the first 600 characters of `H.text()`. Stop servers and exit 1.
  7. On success, print `DEMO CHECK PASSED: <n> beats; filmed doctor 58 s, nurse 58 s, patient 58 s, total 180 s`. Stop servers. Remove the data dir unless `--keep-data`. Exit 0.
  `stop()` also runs in `finally` and on SIGINT/SIGTERM.
  Makefile:
  ```make
  demo-check:
  	$(PY)/python eval/p2/make_media.py
  	$(PY)/python eval/p3/make_clips.py
  	$(PY)/python eval/p4/make_photos.py
  	cd frontend && node --test 'scripts/demo/*.test.mjs' && node scripts/demo/run.mjs
  ```
- [ ] **Step 4:** Run `node --test 'scripts/demo/*.test.mjs'`. Expected: PASS.
- [ ] **Step 5: Dry run.** First confirm `lsof -i :8200 -i :5273` is empty. Run `cd count-guard && make demo-check`. For each beat that fails, decide one of two cases:
  - (a) The expected string is wrong and the app is right by the spec. Fix `beats.mjs`.
  - (b) The app is wrong. Write the beat id, the screen text and the spec line in the commit body, under "Defects for Task 5". Do not fix the app in this task.
  To see the beats before a (b) beat, run with `CG_DEMO_UNTIL=<id>`. Exit 3 never counts as a pass. Every **(confirm)** string ends as confirmed, corrected, or a listed defect.
- [ ] **Step 6:** Confirm `lsof -i :8200 -i :5273` is empty after the run. Confirm `git status` shows no `demo-shots/` and no media. Run the full suites. Expected: all pass, and the build is OK.
- [ ] **Step 7: Commit** `Count Guard v2 P5: make demo-check runs the offline video script in a headless browser`.

### Task 4: The video script doc and its drift test

**Files:**
- Create: `docs/demo/count-guard-v2-video-script.md` (repo root `hackathon26/docs/demo/`; D15 asks for it)
- Create: `count-guard/frontend/scripts/demo/doc.test.mjs`

**Interfaces:**
- Consumes: `BEATS`, `MEDIA`, `ADVICE` from `beats.mjs` (as corrected by Task 3).
- The doc path from the test: `new URL("../../../../docs/demo/count-guard-v2-video-script.md", import.meta.url)`.

- [ ] **Step 1: Write the failing test.** `doc.test.mjs`:
  - `the script doc exists`.
  - `every beat id appears in backticks`: `` `kumar-tray` `` and so on.
  - `every expected string appears verbatim`: for each beat, each `expect`.
  - `every media file name appears`.
  - `the switches and clip names appear`: `TRAY_LIVE`, `SETUP_LIVE`, `MEDICINES_LIVE`, `tray-hernia.mp4`, `saline-setup.mp4`, `make demo-check`.
  - `the sections exist`: headings containing "Offline", "Keyed" and "Owner handover".
  - `narration passes the no-advice regex`: every line starting `> ` (the narration quote style) has no `ADVICE` match.
  - `no key value is written`: no match for `/(MODEL_API_KEY|BASETEN_API_KEY)=\S/`.
- [ ] **Step 2:** Run it. Expected: FAIL (no doc).
- [ ] **Step 3:** Write the doc. Follow the owner's doc rule: a one-page summary first, decisions before detail, `file:line` in an appendix. Sections in order:
  1. **Summary.** The three paths in one line each. The time table: doctor 58 s, nurse 58 s, patient 58 s, intro and close 6 s, total 3:00. How to check it: `make demo-check`, about N minutes, screenshots in `count-guard/demo-shots/`.
  2. **Before filming.** Run the three generators (or `make demo-check` once). Start a clean offline server on the owner's own ports with a fresh data folder: `make dev MODEL_API_KEY= COUNT_GUARD_DATA=/tmp/cg-film`. Open a new private window, because the ward state lives in session storage. Do not press Reset in the first second. Use a 1200-wide window. The patient beats can be filmed in a phone-sized window.
  3. **The script, offline.** One subsection per path (Das, Kumar, Iyer). Each beat is a block: `` `id` ``, start time (mm:ss), role, seconds; numbered clicks naming each control and file; "On screen:" with the expected strings verbatim; the narration as a `> ` quote. Check-only beats are marked "check only, not filmed".
  4. **Keyed variant.** What changes per beat: labels, prose answers, live speech through Record or the WAV files. The model calls per beat (the table above). The three switches, with `file:line`, what each cuts, and the D3 order (saline video first, medicine photo second). `make cost CLIP=eval/p3/tray-hernia.mp4` for the SAM bill before a keyed run. A warning: the owner's `make dev` loads the Meta key, so a keyed run spends credits on every model beat. Drawn stand-in clips give poor live SAM results, so set `TRAY_LIVE`/`SETUP_LIVE` to `False` until the real clips exist (P3-R24).
  5. **Owner handover.**
     - The switches.
     - Clip and photo names the prepared results key on: `tray-hernia.mp4`, `saline-setup.mp4`, the photo stems in `backend/app/journey/prepared/`.
     - What to film: the tray with one needle holder held back, then complete. The saline set-up showing bag, line, cannula and label.
     - Keyed vs offline: offline is the safe default, and the run checks it.
     - Known limits:
       - Offline multi-photo checks follow the first file (upload the intended one first).
       - The offline bot quotes record lines instead of writing prose.
       - The media are drawn stand-ins until filmed (D12, P2-R2).
       - NC-licensed footage is excluded (P3-R1).
       - The tray list is sourced from open incisional hernia counts, though the title says inguinal (P3 Task 1).
       - Iyer's card uses the hernia care template (P5-D11).
       - `/journey` and its Play button still open by URL (P5-D1).
       - One doctor only.
       - The role switcher is a lens, not a sign-in.
  6. **Appendix:** `file:line` for each switch, generator and route the doc names.
- [ ] **Step 4:** Run `node --test 'scripts/demo/*.test.mjs'`. Expected: PASS.
- [ ] **Step 5: Commit** `Count Guard v2 P5: click-by-click video script for the three paths, with owner handover`.

### Task 5: `make demo-check` green, defects fixed

**Files:**
- Modify: whatever the Task 3 defect list and this run find broken, with tests in the module's existing test file or `backend/tests/test_p5_demo_data.py`.
- Modify: `beats.mjs` and the doc together only when a beat's text changes.

- [ ] **Step 1:** Take the "Defects for Task 5" list from the Task 3 commit body. For each defect whose fault is in pure logic, write the failing test first (pytest, or `node --test` on the care module), see it fail, fix it, and see it pass. A render-only fault gets no unit test; the run's beat is its test (as in P4 Task 7). Keep every no-advice and own-record rule.
- [ ] **Step 2:** Run `cd count-guard && make demo-check` with no `CG_DEMO_UNTIL`. Expected: `DEMO CHECK PASSED: 30 beats; filmed doctor 58 s, nurse 58 s, patient 58 s, total 180 s`, exit 0. Fix any further failure as in Step 1 and re-run.
- [ ] **Step 3: Failure path (Review Focus 3).**
  1. Change one `expect` of `kumar-tray` to `"never shown"`.
  2. Run `make demo-check`. Expected: exit code 1, `DEMO CHECK FAILED at beat 13 kumar-tray`, `demo-shots/13-kumar-tray-FAIL.png` exists, and `lsof -i :8200 -i :5273` is empty.
  3. Restore the string.
  4. Repeat the run, pressing Ctrl-C during beat 7 or later. Expected: the ports are free afterwards.
- [ ] **Step 4:** Run `make demo-check` a second time in a row. Expected: PASS again (no flaky beat). If a beat passes only on retry, raise that wait to a `waitText` on the specific string. Never use a longer fixed sleep.
- [ ] **Step 5:** Run the full suites, including `node --test 'scripts/demo/*.test.mjs'` (the doc test catches any beat text changed in Step 1). Expected: all pass, and the build is OK. Confirm `lsof -i :8200 -i :5273` is empty and `git status` shows no media or `demo-shots/`.
- [ ] **Step 6: Commit** `Count Guard v2 P5: demo check green; fixes found by the run`. In the body, list each defect with its test and the final PASS line.

---

## Out of scope (decided)

- Running the keyed variant, or any model call (D11, P2-R1).
- Filming, the voice-over, or editing the video. The owner films from the doc.
- Removing `/journey`, its Play button, the backend `/play` route, or the Guide's Journey card (P5-D1).
- A whole-page no-advice scan in the run. The page also shows exempt text (Das's question contains "take"). App strings are covered by the existing tests, and the narration is covered by `beats.test.mjs` and `doc.test.mjs`.
- A second care template for Iyer (P5-D11).
- A second BP reading by voice during Iyer's saline (spec path, "BP readings by voice"). There is only one prepared BP clip, and it reads 82 again. The film shows the collapse reading by voice; the doc says the 15-minute readings are compressed out.
- Downloading a browser automatically (P5-D3).
- `finishing-a-development-branch`, merge or push. The rulings list goes to the owner at the end of the P1–P5 run (P1-R13).
