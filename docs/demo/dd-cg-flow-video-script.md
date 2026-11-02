# One patient, two apps: video script (Doctor Dictation → Count Guard)

## Summary

The film is 3:00 for the hackathon judges (spec U7). One synthetic patient, **M. Fernandes, 52 F (synthetic)**,
goes from a clinic visit in Doctor Dictation (DD) to the Count Guard (CG) ward, theatre and discharge. It is recorded
from the finished code with every live switch on, scene by scene, and spliced.

The script below is the beat table in `count-guard/frontend/scripts/demo/beats.mjs`: 20 beats, same ids, same order,
same seconds. `make demo-check` walks every beat offline in a headless browser, so each row is proven by a run before
it is filmed. `frontend/scripts/demo/doc.test.mjs` fails if this table and the beat table drift apart.

The film must make three points (`docs/hackathon/03-hackathon-spec.md:8-9`). Each is one beat:

- **(a) The theatre gets context, not just alarms:** `theatre-card` (1:21–1:31). The blood pressure falls and a
  context card sets the numbers side by side, worded from the record. No alarm sounds.
- **(b) A missing swab is caught with a frame as proof:** `theatre-missing` (1:41–1:51). The swab camera names the
  sponge it did not see back and shows the last frame it saw it in.
- **(c) The discharge draft wrote itself from the timeline:** `discharge-draft` (2:05–2:19). One press, and the
  draft holds the prescription, the drug given and the count, each from the record.

Both apps show the banner **"Research demo · Synthetic data · Not for clinical use"** on every screen, so "synthetic
data" and "research demo" are on screen throughout (`03-hackathon-spec.md:109`). The context card adds its own
"Research demo — not for clinical use".

## Scenes

| Time | Scene | Beats | Seconds |
|---|---|---|---|
| 0:00–0:10 | Title: one synthetic patient, two apps | 1 | 10 |
| 0:10–0:40 | DD: dictate → Save & admit to ward | 3 | 30 |
| 0:40–1:05 | Ward: arrival, wristband photo Accepted, wrong photo Not accepted, retake | 4 | 25 |
| 1:05–2:05 | Theatre: drug by voice, context card, swab camera, missing swab and its last frame, the hard stop | 7 | 60 |
| 2:05–2:45 | Discharge: Draft discharge, sign, the PDF, home | 4 | 40 |
| 2:45–3:00 | Close: "The system formats. The doctor decides." | 1 | 15 |

## The script

"Banner" means the line "Research demo · Synthetic data · Not for clinical use" at the top of the app in view.
Narration is plain description: no line tells anyone what to do for a patient (it passes the `ADVICE` regex in
`beats.mjs`).

| Time | Scene | Beat | s | On-screen action | Narration | Labels on screen |
|---|---|---|---|---|---|---|
| 0:00–0:10 | Title | `title` | 10 | Both apps side by side: DD at http://127.0.0.1:8300/, CG at http://127.0.0.1:5273/ with role Doctor. The CG dock reads "models: live". | One synthetic patient, two apps: Doctor Dictation in the clinic and Count Guard on the ward and in theatre, on live Meta models. | Banner in both apps: Research demo · Synthetic data |
| 0:10–0:16 | DD | `dd-open` | 6 | Full screen on DD. The "Tap to dictate" button. | Dr. Rao opens Doctor Dictation for a new clinic visit. | DD banner: Research demo · Synthetic data |
| 0:16–0:30 | DD | `dd-dictate` | 14 | Tap to dictate, speak the dictation line (below), tap again. The form fills. Check it, and correct it if needed (cut the correction between takes): Name "M. Fernandes (synthetic)", Age/Sex "52 F", medicine "Paracetamol 500 mg 1-1-1". Save only when the page reads "All medicines are ready. You can Save." | She dictates the visit; the prescription fills itself and every medicine is checked. | DD banner: Research demo · Synthetic data; patient name ends "(synthetic)" |
| 0:30–0:40 | DD | `dd-admit` | 10 | Save & admit to ward → type "Right inguinal hernia repair" in Reason for admission → Save & admit to ward. Status: "Saved. Sending to Count Guard…", then "Saved and in Count Guard." | She types the reason and saves with Save & admit to ward; the page says when Count Guard has the patient. | DD banner: Research demo · Synthetic data |
| 0:40–0:47 | Ward | `ward-arrival` | 7 | Switch to CG, role Nurse, tab Patients. "M. Fernandes, 52 F" is listed, "Being admitted". | On the Count Guard ward, Nurse Meena sees Ms. Fernandes arrive, being admitted, with the clinic prescription. | CG banner: Research demo · Synthetic data |
| 0:47–0:53 | Ward | `ward-photo-ok` | 6 | Open the chart. Wristband photo into "Photo check: Wristband on". "Accepted — The photo shows a patient wristband…". The "Doctor Dictation PDF" link is on the chart. | She photographs the wristband; the photo check accepts it and says what it saw. | CG banner: Research demo · Synthetic data; live verdict has no "Prepared" |
| 0:53–0:59 | Ward | `ward-photo-wrong` | 6 | Bed-rail photo into "Photo check: Consent on file". "Not accepted — …", with "Reason to override". | A photo of the bed rail is sent for the consent form; the check does not accept it, and the item stays open. | CG banner: Research demo · Synthetic data |
| 0:59–1:05 | Ward | `ward-retake` | 6 | Take the photo again with the consent form → "Accepted". Tick the four admission boxes → Complete admission → "On the ward". | She takes the photo again with the signed form, ticks the checklist and completes the admission. | CG banner: Research demo · Synthetic data |
| 1:05–1:11 | Theatre | `theatre-send` | 6 | Role Doctor. Procedure: hernia repair → Send to theatre → "In theatre". | Dr. Rao picks the hernia repair and sends her to theatre. | CG banner: Research demo · Synthetic data |
| 1:11–1:21 | Theatre | `theatre-drug` | 10 | Role Nurse. Lignocaine recording into "Upload audio" in "Drug given" → Add heard line ("Heard, not confirmed") → Confirm given. Row: "lignocaine 2% 5 ml local infiltration", "From voice", "confirmed by Nurse Asha". | In theatre the local anaesthetic is said aloud; the heard line is drafted, and the nurse confirms it was given. | CG banner: Research demo · Synthetic data; "From voice" |
| 1:21–1:31 | Theatre | `theatre-card` | 10 | Next reading four times: "BP 86/50 · HR 76 · Simulated". Tick "Context card (research tier)". Card: "BP 86/50, down 28% in 4 min. HR not rising." | The simulated pressure falls. Instead of an alarm, the context card sets the numbers side by side, worded from the record. | CG banner: Research demo · Synthetic data; "Simulated"; card: "Research demo — not for clinical use"; "Worded by AI from the record" |
| 1:31–1:41 | Theatre | `theatre-camera` | 10 | Surgery began → Record pack opened (15) → Start the swab camera → the theatre clip (see "The swab camera" below). "Advice only. The count a person saves decides." | Surgery begins, the pack is recorded, and the swab camera watches the theatre clip. | CG banner: Research demo · Synthetic data; "Advice only"; "Read by camera" ("· Prepared" on the recorded clip) |
| 1:41–1:51 | Theatre | `theatre-missing` | 10 | Scroll to "One lap sponge was not seen back. It was last seen on the sterile field." Hold on the image "Last frame the camera saw it in". | One sponge was not seen back, and the camera shows the last frame it was seen in, as proof. | CG banner: Research demo · Synthetic data; "Advice only" |
| 1:51–1:59 | Theatre | `theatre-hard-stop` | 8 | Type 14 in "Closing count (returned)". "What did the team do? (required)" and "Surgery ended unlocks when the count is saved." | The nurse types 14 back of 15; the reason is required, and surgery cannot end until a person saves the count. | CG banner: Research demo · Synthetic data |
| 1:59–2:05 | Theatre | `theatre-reconcile` | 6 | On the advice: "Found under the drape, counted by hand" → Acknowledge. Count 15 → Save count as Nurse Asha → Surgery ended → Back to ward. | The sponge is found under the drape; she notes it on the advice, saves 15 of 15, and surgery ends. | CG banner: Research demo · Synthetic data |
| 2:05–2:19 | Discharge | `discharge-draft` | 14 | Role Doctor → Draft discharge. "Drafted from the record": "Paracetamol 500 mg 1-1-1", "lignocaine 2% 5 ml local infiltration · by Nurse Asha", "opened 15 / returned 15, 0 unaccounted · saved by Nurse Asha". | Dr. Rao presses Draft discharge. Nobody typed it: the draft wrote itself from the timeline, with the prescription, the drug given and the count. | CG banner: Research demo · Synthetic data; "Drafted from the record" |
| 2:19–2:25 | Discharge | `discharge-sign` | 6 | Sign discharge → "Being discharged". The "Discharge PDF" and "Follow-up in calendar" links appear. | She checks the summary and signs the discharge. | CG banner: Research demo · Synthetic data |
| 2:25–2:33 | Discharge | `discharge-pdf` | 8 | Open the Discharge PDF: the drug log line and "Opened 15. Returned 15. Unaccounted 0." Then the follow-up calendar file. | The signed discharge PDF opens with the drug log and the count, and the follow-up goes to the calendar. | PDF header: Research demo; CG banner: Research demo · Synthetic data |
| 2:33–2:45 | Discharge | `discharge-home` | 12 | Role Nurse. Discharge card photo and medicine bag photo into their checks (both Accepted). Tick the three boxes → Complete discharge → "Home". | The nurse photographs the discharge card and the medicine bag, ticks the checks, and Ms. Fernandes goes home. | CG banner: Research demo · Synthetic data |
| 2:45–3:00 | Close | `close` | 15 | Tab My patients; the doctor's status reads "Available". Hold. | Back on My patients, every step has a record. The system formats. The doctor decides. | CG banner: Research demo · Synthetic data |

**The dictation line** (`dd-dictate`), spoken by the doctor at a normal pace:
"M. Fernandes, 52 year old woman, synthetic patient. Right inguinal hernia, painful for two weeks. Tablet paracetamol
500 mg three times a day after food for five days. Admit for hernia repair." It is the transcript the offline check
uses (`frontend/scripts/demo/dd.mjs`). Offline, the form comes from a fixed stub form, not from this text. Live, the
model writes the form, so it may differ. Before Save, correct it on screen:

- Name must read exactly "M. Fernandes (synthetic)". Count Guard writes the ward name "M. Fernandes, 52 F
  (synthetic)" only when the DD name already ends in "(synthetic)" (`count-guard/backend/app/journey/intake.py:30-37`).
- Age/Sex must read "52 F".
- The medicine row must read Tab. Paracetamol 500 mg, 1-1-1, after food, 5 days. Later beats show "Paracetamol 500 mg
  1-1-1" in the discharge draft.
- "All medicines are ready. You can Save." must show before Save.

**Narration notes.** Five lines differ from the beat `say` lines, for the live film: `title` (live models, not
offline), `theatre-card` and `discharge-draft` (criteria (a) and (c) said in words), `theatre-camera` ("the theatre
clip", since it may be the prop clip), `theatre-missing` ("as proof", criterion (b)). Every other line is the beat's
`say` line word for word.

## The swab camera (the one known risk)

"Play the recorded theatre clip" always runs the recorded scenario. It is labelled "Prepared" whatever the switches
say (`count-guard/backend/app/journey/camera_api.py:183-188`). Only "Add theatre video" sends a clip to live SAM 3.1
(`camera_api.py:95-108`, concepts "gauze swab" and "lap sponge").

Live SAM found **0 swabs** on the drawn tray image `swab-tray-synthetic.png` (Task 11 live-check, 2 Nov). The drawn
clip `swab-count/swab-leaving-field.mp4` is drawn the same way, so it will likely fail too. Recommendation: film a
**real prop swab tray** (allowed by spec U14) and send that clip to the live camera.

How to make and use the prop clip:

1. Lay out real white gauze swabs or lap sponges, well apart, on a plain green or blue cloth. No faces, hands only.
2. Film 10–15 s from straight above, phone on a stand, good light. Partway through, a gloved hand lifts one swab and
   carries it out of frame. The rest stay still.
3. Save it as `count-guard/eval/media/swab-count/swab-prop-tray.mp4` (git-ignored) and add a row to
   `count-guard/eval/media/SOURCES.md`: "recorded for this project", role `demo` (U14).
4. Check the spend first: `make cost CLIP=eval/media/swab-count/swab-prop-tray.mp4` (from `count-guard/`).
5. In `theatre-camera`, type the number of prop swabs in "Record pack opened" instead of 15, then use **Add theatre
   video** with the prop clip. The row reads "Read by camera" with no "Prepared".
6. Keep the take only if the advice names one swab not seen back with its last frame. In `theatre-hard-stop` and
   `theatre-reconcile`, type one less, then the full number. Use these lines instead of the numbered ones.

   `theatre-hard-stop` with the prop clip:

> The nurse types one fewer than the pack; the reason is required, and surgery cannot end until a person saves the count.

   `theatre-reconcile` with the prop clip:

> The swab is found under the drape; she notes it on the advice, saves the full count, and surgery ends.

7. The prop count carries forward. In `discharge-draft` the count line reads "opened N / returned N, 0 unaccounted",
   and in `discharge-pdf` the PDF reads "Opened N. Returned N. Unaccounted 0.", where N is the prop count, not 15.
   The narration of both beats names no number, so it still holds.

If the live run finds no missing swab after two tries, film the recorded clip instead. The "Prepared" label stays on
screen and the narration says "the theatre clip", which is true of both.

## How to record

### Before the take

1. Wait for the freeze: 3 Nov 18:00 IST (U11). Record from the frozen code.
2. Make the media, from `count-guard/`: `.venv/bin/python eval/make_media.py`. Use the files with role `demo` in
   `count-guard/eval/media/SOURCES.md`:
   - `wristband/wristband-synthetic.png` (`ward-photo-ok`)
   - `wrong-photo/wrong-photo-bed-rail-synthetic.png` (`ward-photo-wrong`)
   - `consent/consent-form.png` (`ward-retake`)
   - `drug-phrases/drug-lignocaine.wav` (`theatre-drug`)
   - `discharge/discharge-card.png` and `medicine-bag/medicine-bag-synthetic.png` (`discharge-home`)
   - the prop clip from "The swab camera" above (`theatre-camera`)
3. Run `make demo-check` once (from `count-guard/`). It must pass. Then make sure it is not running: it uses the
   same ports 8200, 5273 and 8300 as the recording.
4. Optional, spends credits: `make live-check` (from `count-guard/`) makes one real call per model.

### Start both apps by hand

Each take starts from empty databases. Run from the repo root in a first terminal:

```sh
rm -rf /tmp/dd-cg-film && mkdir -p /tmp/dd-cg-film/cg
openssl rand -hex 16 > /tmp/dd-cg-film/token     # the shared intake token; never shown on screen
```

Second terminal, Doctor Dictation on 8300 (single clinic, fresh database, banner on, Muse speech and Spark text):

```sh
cd doctor-dictation
set -a; . ../.env; set +a                        # loads the Meta key from the root .env; prints nothing
export MULTI_CLINIC= DEMO_BANNER=1 DB_PATH=/tmp/dd-cg-film/dd.db \
       STT_ENGINE=muse LLM_PROVIDER=meta \
       COUNT_GUARD_URL=http://127.0.0.1:8200 CG_SYNC_TOKEN="$(cat /tmp/dd-cg-film/token)"
.venv/bin/python -m uvicorn doctor_dictation.main:app --host 127.0.0.1 --port 8300
```

Third terminal, Count Guard on 8200 (API) and 5273 (web), every live switch on:

```sh
cd count-guard
set -a; . ../.env; set +a                        # the same key; prints nothing
export DD_BASE_URL=http://127.0.0.1:8300 CG_SYNC_TOKEN="$(cat /tmp/dd-cg-film/token)" \
       VOICE_LIVE=1 PROOF_LIVE=1 SPARK_LIVE=1
make dev CG_API_PORT=8200 CG_WEB_PORT=5273 COUNT_GUARD_DATA=/tmp/dd-cg-film/cg
```

Never echo the key, and never film a terminal. If a key must be checked, check that it is set
(`[ -n "$META_API_KEY" ] && echo set`), not its value.

### Live switches

| Switch | Where | How it is on for the film |
|---|---|---|
| `VOICE_LIVE` | env, `count-guard/backend/app/config.py:122` | `VOICE_LIVE=1` (above) |
| `PROOF_LIVE` | env, `config.py:123` | `PROOF_LIVE=1` |
| `SPARK_LIVE` | env, `config.py:124` | `SPARK_LIVE=1` |
| `TRAY_LIVE`, `SETUP_LIVE`, `SWABS_LIVE`, `MEDICINES_LIVE` | constants in `count-guard/backend/app/journey/switches.py:20-23` | `True` in the code; leave them. They are live when the key is set. |
| DD speech and text | DD env | `STT_ENGINE=muse`, `LLM_PROVIDER=meta` |

Check before the first take:

```sh
curl -s http://127.0.0.1:8200/journey/models      # "live": true and every switch true
curl -s http://127.0.0.1:8300/health | python3 -m json.tool | grep -E '"(llm_provider|stt_engine_requested|stt_engine_active|meta_configured|demo_banner)"'
```

DD must show `llm_provider` "meta", `stt_engine_requested` "muse", `stt_engine_active` "muse-api" (the display
name), `meta_configured` true, `demo_banner` true. The CG
dock must read "models: live".

### During the take

- One browser window, 1200 px wide, a new private window per take. DD and CG in two tabs.
- Record each scene as its own clip and splice. The patient's state carries forward, so record the scenes in order.
- A live step that fails or is slow is **re-shot**: keep recording, retry (for a photo: "Take the photo again"), and
  cut the failed part out. If the patient's state is wrong, start over from "Start both apps by hand".
- A failed photo check reads "Not checked — model unavailable" and keeps the item open. That is correct but not the
  film; re-shoot it.
- A step that fell back to its prepared result shows "Prepared". Use such a shot only with the label in view and
  only when a live retry has failed twice; note it in the recording log.
- Captions on (`03-hackathon-spec.md:109`).

### Recording log (for the submission notes)

The submission notes say what was live and what was replayed (`03-hackathon-spec.md:111`). For each beat write: live
or Prepared, the take used, and for the swab camera which clip (prop, live or recorded, Prepared).

Check DD dictation for each take. `/health` reporting "muse-api" does not prove the take used Muse: the chain can
fall back to local faster-whisper without a visible error. The dictation is live only when the take's
`/api/transcribe` response has `"engine": "muse:muse-voice-transcribe-1.0"`. Find it in the browser's dev tools,
Network tab (`doctor-dictation/doctor_dictation/providers/stt/muse.py:62`). If it reads `local:…` (faster-whisper) or
another engine, log the take as not live and re-shoot it.

### Deadlines

- Freeze: **3 Nov 18:00 IST**, then record (U11).
- Submission: **4 Nov** (`03-hackathon-spec.md:5`).
- The Meta API credits must be **claimed by the user before 4 Nov 9 PM ET** (`count-guard/docs/loop/backlog.md:122`).
  This is a task for the user; no code does it.
- No spend limit until 4 Nov (U15): re-run live steps as often as the film needs.
