# Doctor Dictation Demo

Voice → cloud STT (OpenAI Whisper) → LLM `json_object` → editable prescription → Save & Print (SQLite + PDF).

## Run (same folder — venv first)

```powershell
cd C:\work\project-doc\doctor-dictation   # this app now lives in doctor-dictation/ of the hackathon26 repo
py -3.12-arm64 -m venv .venv-arm64
.\.venv-arm64\Scripts\python -m pip install --upgrade pip
.\.venv-arm64\Scripts\python -m pip install -e .
# extras: ".[stt]" local faster-whisper, ".[pdf]" PDF render, ".[dev]" tests
copy ..\.env.example ..\.env   # one .env at the workspace root, shared with count-guard
# edit .env -> set OPENAI_API_KEY for cloud STT + default LLM formatting
# (optional; without any key a rules-fallback formats the seeded example)
.\.venv-arm64\Scripts\python -m uvicorn doctor_dictation.main:app --port 8000 --reload
# open http://127.0.0.1:8000  (use 127.0.0.1, not localhost: proxy setups can hang localhost)
# --reload picks up code edits without restart; Ctrl+F5 after frontend changes (app.js is versioned)
```

## STT note (Python versions)
`faster-whisper` declares `requires-python >=3.9`, but its key dependency
`ctranslate2` only ships Windows wheels for **CPython 3.9–3.14 on x64
(`win_amd64`)** — verified on PyPI 2026-10-11. So in practice:
- ✅ Python **3.11 / 3.12 x64** — fully supported, prebuilt wheels (recommended).
- ⚠️ Python 3.13 / 3.14 x64 — latest `ctranslate2` has wheels, less battle-tested.
- ❌ Python **3.15** — no `ctranslate2` wheels yet, `pip install faster-whisper` fails.
- ❌ Python **ARM64-native** — `ctranslate2` ships `win_amd64` only, no `win_arm64`.

This machine is ARM64, so this repo uses two venvs:
```
.venv-arm64 -> Python 3.12 ARM64 (native): UI + OpenAI/DeepSeek formatting, tests
.venv-stt   -> Python 3.12 x64 (emulated): + local faster-whisper
.\.venv-stt\Scripts\python -m uvicorn doctor_dictation.main:app --port 8000
```
(The old `.venv` on Python 3.15 still works but is no longer the documented default.)
Without `.venv-stt`, `/api/transcribe` uses cloud STT when `OPENAI_API_KEY` is
set. With no key and no local model it returns 503 and the page surfaces that
error (install the x64 venv, or set a key).

## Flow (dictation-first)
1. 🎤 **Start dictation** — dictate the whole visit, including patient demographics
   ("patient Rahul Sharma, 45 year old male") and an OP/registration number if
   known. Stop. `POST /api/transcribe` returns the transcript, then
   `POST /api/format` structures it into the PATIENT CLINICAL SUMMARY &
   PRESCRIPTION sheet. There is **no model picker** — STT is cloud-first (see below).
2. The sheet is an **editable form**: every field (demographics, lists, and each Rx
   row) is editable in place. Hand-editing a medicine clears its verification, so an
   edited row can never keep a stale ✓.
3. **Dictate a correction** — once a draft exists the mic applies a spoken change to
   the current form (`POST /api/v1/correct`), merging only the fields the correction
   names. The form is re-grounded and previous confirmations are dropped.
4. **Verify gate** — every Rx row must be `verified` or explicitly confirmed
   (per-row Confirm, or "Confirm all"). `Save & Print` is blocked (409) while any
   row is unchecked, and the page lists the open rows to confirm.
5. **Save & Print** — `POST /api/v1/documents` upserts the patient (matched by OP
   number) and records a finalized encounter, the document, and an audit entry in
   SQLite, renders a PDF, then opens the browser print dialog (print CSS prints
   only the sheet).

## Workspace (UI)
The page at `http://127.0.0.1:8000` is a three-pane clinic workspace with a top bar:

- **Top bar** (not printed): the clinic/doctor name, the assistant status chip, a
  health badge (active STT engine • configured LLM), **↺ New patient** (clears the
  screen to start the next visit), and **⚙ Profile** (opens the clinic-profile
  settings panel).
- **Today** sidebar (left, not printed): the documents saved today — one row per
  saved document — see below.
- **Middle** (not printed): the dictation mic, the three coarse assistant steps,
  status / error + Retry, the transcript, and the "confirm these medicines" panel.
- **Right**: the editable prescription document (`#sheet`); only the sheet prints
  (print CSS), with **Save & Print** beneath it.

### Assistant steps
Status is deliberately coarse and truthful — **Listening → Working → Ready** (plus
**Idle**), mirrored by the top-bar chip. *Listening* while recording, *Working*
during STT / format / correct, *Ready* once a draft or reopened document is on the
sheet, *Idle* otherwise. The step holds at *Ready* through **Save & Print** (saving
only updates the buttons/status, not the step). There is no invented per-tool
progress.

### Today's list, reopen, and in-place re-save
- **Today** calls `GET /api/v1/encounters/today`, returning the documents saved in
  the server-local calendar day (patient name, OP no, save time, `document_id`).
- Clicking a patient calls `GET /api/v1/documents/{document_id}` and loads that saved
  prescription back onto the sheet for review or re-print. The right pane notes
  "Editing today's document #N — Save & Print updates it in place."
- Saving a reopened document sends `document_id` in the `POST /api/v1/documents`
  body. The verify gate still runs first, then the existing document row is
  **updated in place** (no duplicate), reusing its encounter and that encounter's
  patient — the patient is never re-upserted from the payload. A fresh save omits
  `document_id` and upserts the patient (by OP number) plus a fresh
  encounter/document.

## Clinic profile
- `GET /api/v1/profile` returns the six fields (`doctor_name`, `qualifications`,
  `reg_no`, `clinic_name`, `address`, `phone`); unset fields default to `""`.
- `PUT /api/v1/profile` upserts the single clinic-profile row (id=1) and returns it.
- The **⚙ Profile** panel edits these fields; the top bar shows the clinic and doctor
  name. The profile is rendered as a centred header at the top of the sheet and of
  the server-generated PDF (`doctor_dictation/pdf.py`), so it prints on every prescription.
  Blank fields are omitted; with no profile saved, nothing is printed there.

## Multi-clinic sign-in
Single mode (`MULTI_CLINIC` off, the default) has **no sign-in**: anyone who can reach the server can use it.
To give each clinic its own data and logins:
1. Set `MULTI_CLINIC=1`, `DATA_DIR=<folder>` and `SESSION_SECRET` in `.env`. Generate the secret with
   `python -c "import secrets; print(secrets.token_urlsafe(48))"` (the app refuses to start without it).
2. Create a clinic and its first user: `python -m doctor_dictation.admin create-clinic --slug rao --name "Rao Clinic" --first-user dr.rao`.
   A temporary password is printed once.
3. Start the app: `uvicorn doctor_dictation.main:app`. Behind a proxy add `--proxy-headers --forwarded-allow-ips=<proxy>` (for example `127.0.0.1`).
4. SQLite 3.35 or newer is required (the app refuses to start in multi-clinic mode otherwise).
5. Open the site; it redirects to `/login`. The first sign-in forces a password change.
- More users: `python -m doctor_dictation.admin create-user --clinic rao --username dr.shah --display-name "Dr. Shah" --role doctor` (`--role` is `doctor`, `assistant` or `admin`).
- Keep today's single-clinic data: stop the app, then `python -m doctor_dictation.admin adopt-existing --slug rao --first-user dr.rao`.
- Forgotten password: `python -m doctor_dictation.admin reset-password --user dr.shah` (prints a new temporary password and ends that user's sessions).

## Multi-clinic demo (about 5 minutes)
Fake data only. `seed-demo` refuses to run unless `DEMO_MODE=1`, and only into a new, empty data folder (never the
default `doctor_dictation/data`). Its three doctors have fixed, published demo passwords (`demo-rao-pass-1`,
`demo-mehta-pass-1`, `demo-iyer-pass-1`, also printed by the command), so never point it at real data. The stub
providers need no API key: dictation is canned (it always produces the same fever prescription for "Kiran Joshi").

```bash
export DEMO_DIR="$(mktemp -d)" MULTI_CLINIC=1 DEMO_MODE=1
export DATA_DIR="$DEMO_DIR" SESSION_SECRET="$(python -c 'import secrets; print(secrets.token_urlsafe(48))')"
eval "$(python scripts/demo_browser.py --print-env)"   # stub STT and LLM: ALLOW_STUB_PROVIDERS=1 STT_CHAIN=stub LLM_PROVIDER=stub ...
python -m doctor_dictation.admin seed-demo         # Rao Clinic: dr.rao, dr.mehta; Iyer Clinic: dr.iyer
uvicorn doctor_dictation.main:app --port 8000
```

Use two browsers, or one normal and one private window (one window per clinic: they must not share cookies).
1. Sign in as `dr.rao` in one window and `dr.iyer` in the other: different clinic names and different Today lists.
2. Rao dictates and saves: it appears in Rao's Today only. Open `/api/v1/documents/1` in each window: both clinics
   have a document 1, with different patients.
3. Sign in as `dr.mehta` (a third window, or after Rao signs out), switch Today to "Whole clinic" and open Rao's
   prescription: a "view only" banner, mic and Save disabled. Print works and shows Dr. A. Rao as the author. The
   reprint lists BOTH Dr. A. Rao and Dr. S. Mehta because Rao Clinic's shared pad lists all its doctors. A re-save is refused.
4. Print a Rao Clinic prescription: the shared letterpad lists both doctors. Print an Iyer Clinic one: its own letterhead.
5. Copy the PDF link of Rao's new prescription (`/api/v1/documents/<id>/pdf`) into Iyer's window: 404.
6. Show the audit actors and the folder: `sqlite3 "$DEMO_DIR/clinics/rao/app.db" "SELECT actor, action FROM audit_log"`
   (and the same for `iyer`), then `ls -R "$DEMO_DIR"`: `directory.db` plus one `app.db` per clinic.

When done, stop the server (Ctrl+C) and delete the demo data: `rm -rf "$DEMO_DIR"`.

Automated run with screenshots for review: `scripts/demo_browser.py` (writes to `.superpowers/demo-evidence/`). It needs
Playwright (`pip install -r doctor_dictation/requirements-pdf.txt && python -m playwright install chromium`; the same
package renders the PDFs) and a server started as above:
`python scripts/demo_browser.py --base http://127.0.0.1:8000 --data-dir "$DEMO_DIR"`. It refuses the default data folder
and any non-loopback server (unless `--allow-remote`). The text checks on the PDFs use `pdftotext` when it is on PATH.

## Notes
- STT: **cloud-first, the default.** With `OPENAI_API_KEY` set, `/api/transcribe`
  sends the recorded audio to the OpenAI Whisper API (seconds, no model load). If
  that call fails it falls back to local `faster-whisper`. `STT_ENGINE=auto` is the
  cloud-first default; `STT_ENGINE=openai|faster-whisper` pins one engine. The local
  fallback model is `small.en`, configurable only via `WHISPER_MODEL` (turbo avoided:
  too slow on CPU). With no cloud key and no local model, transcription is unavailable
  and the page reports it.
- LLM: OpenAI `gpt-6-luna` by default (`LLM_PROVIDER=openai`, `LLM_MODEL` in `.env`; DeepSeek kept via `LLM_PROVIDER=deepseek`) with `response_format: {"type":"json_object"}`. `gpt-6-luna` rejects `temperature` (auto-dropped, default 1); seed + json mode + validator + loop + cache keep output stable. Without any key, backend uses rule fallback so demo still works.
- Privacy: **the audio may leave the machine** — the cloud STT default uploads the
  recording to OpenAI, and the app does **not** save the audio. Only the transcript
  text is sent to the configured LLM provider (OpenAI `gpt-6-luna` by default, or
  DeepSeek). Persisted to SQLite are the structured prescription, the encounter, and
  an audit entry — plus a rendered PDF — not the audio.
- Safety: sheet shows "AI draft — doctor must verify". Never auto-finalize meds.

## Determinism (same input → same sheet)
- STT decode pinned: `temperature=0.0, beam_size=5, patience=1.0, condition_on_previous_text=False` (`STT_DECODE` in `doctor_dictation/main.py`); the server transcript is the single source of truth.
- LLM: `temperature=0, top_p=1, seed=7` (retried without seed if endpoint rejects it), strict enum prompt (dose `1-0-0/1-0-1/1-1-1/0-0-1/SOS`), up to 3 validated retries, Pydantic-style post-validation flags rx names absent from the transcript as `[unverified]`, identical transcripts served from `sha256` cache.
- Agent loop (`extract → ground → targeted repair`, max 3 LLM calls): every rx row is grounded against transcript + medicine list (`verified` / `unverified-name` / `unknown-medicine` / `unverified-strength`); repair prompts name the offending drug; best draft wins; per-row Check pills (✓/?/!/±) in the sheet, print-safe.
- Offline lexicon `doctor_dictation/core/lexicon/drugs.json` (v1.1.0, 444 entries: generics + Indian brands) corrects STT splits/misspellings (`tam sulosin`→Tamsulosin, `crocin`→Paracetamol) with stdlib-only matching — no network at runtime. Brand→generic resolution is file-order independent (regression-tested). Refresh offline via `python doctor_dictation/core/lexicon/build.py`; optional `--enrich` pulls NIH RxNav suggestions into a disk cache (build-time only).
- Gate: `.\.venv-arm64\Scripts\python -m pytest tests/ -q` (8 golden transcripts × 5 runs + API cache + schema + loop + engine tests).

## STT engines
- `STT_ENGINE=auto` (default): cloud (OpenAI) → local faster-whisper (`small.en`). The local fallback is configurable only via `WHISPER_MODEL`; there is no in-app model picker. Pin with `STT_ENGINE=openai|faster-whisper`. `/api/health` reports `stt_engine_active`.
- Cloud STT uploads the audio to OpenAI (see Privacy above); the app never stores the audio.
- **ONNX / Snapdragon engine — DEFERRED (not needed).** No local model is required here; cloud-first STT plus the faster-whisper fallback is sufficient. The interface stub stays in `doctor_dictation/stt_onnx.py` (import-safe; reports unavailable) and `STT_ENGINE=onnx` returns 503. `doctor_dictation/requirements-onnx.txt` is unused. See the Snapdragon plan, Part B.
