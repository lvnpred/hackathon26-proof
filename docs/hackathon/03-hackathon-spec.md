# 03 — Hackathon spec: "One patient, one morning"

## 1. Goal

Ship a **3-minute demo video** and a runnable branch by **4 Nov**, built in **7 days (26 Oct – 1 Nov)**.
The demo must show modules feeding each other on one timeline. Polish only what the camera sees.

Success = a judge understands in 3 minutes that (a) the OT gets context, not just alarms, (b) a missing swab
is caught with a frame as proof, and (c) the discharge draft wrote itself from the timeline.

## 2. Scope

| Priority | Module | Hackathon cut |
|---|---|---|
| **Must** | Shared timeline + OT screen | Table, store, SSE stream, one screen with three panels |
| **Must** | Count Guard | SAM live if spike S1 passes; replay of recorded detections always works |
| **Must** | Voice drug log | Push-to-talk → Muse STT → regex parse → grounded event → confirm tap |
| **Should** | Simulated vitals + context card | One scenario file; three rules; template card + LLM rewording with the wording check |
| **Should** | Discharge draft | Fold → HTML sections → existing PDF renderer; `.ics` follow-up download |
| **Could** | Brown-bag (light) | One photo → vision LLM → grounded list; duplicate flag only with `DECISION_TIER=1` |
| **Won't** | GxP, real monitor/HL7, screen-reading vitals, Tamil, multi-clinic mode, login changes, mobile layout |

## 3. Demo script (filmed on Day 7)

| Time | Scene | On screen | Module proof |
|---|---|---|---|
| 0:00–0:10 | Title | "One patient, one morning" · synthetic patient "R. Kumar, 58 M" | — |
| 0:10–0:50 | **OPD** | Strips tipped onto the desk → photo → list appears: metoprolol 25 mg (beta-blocker), amlodipine 5 mg, … | Brown-bag writes `brownbag.med_found` |
| 0:50–1:15 | **OT: setup** | Nurse says "opening twenty swabs" → count IN 20. Camera on tray and bucket. | Count `pack_opened` |
| 1:15–1:40 | **OT: drug** | Surgeon presses talk: "lignocaine two percent, five ml, local infiltration" → row appears, grounded ✓ | Drug log |
| 1:40–2:10 | **OT: vitals** | Simulated BP slides 120 → 86. Card appears in < 1 s: "BP 86/50, down 28% in 4 min · lignocaine 5 ml 3 min ago (voice log) · on metoprolol (OPD medicine review) · HR not rising · 6 swabs out in 10 min · [hypotension checklist]". Banner: research demo. | Vitals + context, reads 3 modules |
| 2:10–2:30 | **OT: close** | Closing count: IN 20, OUT 19 → "1 swab unaccounted" with its last frame (09:52, near the drape). | Count `closing` |
| 2:30–2:55 | **Discharge** | Click "Draft discharge" → PDF with OPD medicines, drugs given, count result, events. `.ics` downloads. | Discharge fold |
| 2:55–3:00 | Close | "The system formats. The doctor decides." | — |

Record each scene separately. Splice in editing. A scene that fails live is re-shot from the replay path.

## 4. Shortcuts allowed (and not allowed)

| Allowed in the hackathon | Not allowed, even in the hackathon |
|---|---|
| Single-clinic mode, one uvicorn worker | Real patient data, real faces, or anything patient-like sent to Meta APIs |
| Hard-coded demo episode id and patient | The Muse Spark "contributor" tier |
| Replay of pre-recorded SAM detections, labelled as such in the submission | An LLM that adds facts to the card (the wording check stays) |
| A hand-written drug-class map for ~20 demo drugs | Any drug or dose recommendation on screen |
| No frontend tests; manual check against the demo script | Decision-tier output without the research banner |
| Inline CSS, one big `ot.js` (≤ 500 lines still) | Editing existing modules beyond the agreed hooks (§6) |
| Skip `audit_log` rows for `vitals.reading` | Committing `.env` or keys |

## 5. Acceptance checks

Each check is a scripted step a reviewer can run. "Pass" means every listed outcome is seen.

### 5.1 Timeline

- `POST /api/hx/episodes` creates an episode for the demo patient. `GET .../stream` emits each new event
  within 1 s of the write, in `id` order, and resumes from `Last-Event-ID` after a reload.
- A correction creates a new event with `supersedes_id`; the fold shows only the new one.

### 5.2 Count Guard

- Replay mode: playing `detections_demo.jsonl` yields exactly 19 `count.item_out` events and one closing
  discrepancy naming the right `track_id` and frame.
- Waving a swab over the bucket for fewer than `DWELL` frames does not count it (unit test).
- Live mode (if S1 passed): 10 swabs dropped one by one under good light → count within ±1. Record the
  real result in the submission notes, whatever it is.

### 5.3 Voice drug log

- The five demo phrases (in `tests/hx/druglog_phrases.json`) parse to the expected drug, amount, unit, route.
- An unknown drug name lands as "as heard", ungrounded, and needs a confirm tap before it shows ✓.

### 5.4 Vitals and context card

- The scenario fires `bp_drop_pct` once at the scripted time, not repeatedly (cooldown).
- The template card renders before any LLM call returns (measure: card visible < 500 ms after the reading).
- Feeding the wording check an LLM text that contains a new number or "consider giving" → template kept.
- With `DECISION_TIER=0` the card route is 404 and the panel is hidden.

### 5.5 Discharge

- The PDF lists the OPD medicines, every confirmed `druglog.given`, and the closing count result.
- No decision-tier event appears on the PDF in either tier mode.

## 6. Hooks into existing code (the only edits outside `hx/`)

| File | Edit | Size |
|---|---|---|
| `doctor_dictation/api/app.py` | `if os.getenv("HACKATHON") == "1": app.include_router(hx_api.router)` before static mount | ~3 lines |
| `doctor_dictation/db/migrations/011_timeline.sql` | New file (`02` §4.1) | new |
| `doctor_dictation/api/persistence.py` | After a save, write `rx.saved` when `HACKATHON=1` | ~5 lines |
| `.env.example` | `HACKATHON`, `DECISION_TIER`, `VISION_ADAPTER`, `SAM_*` keys, commented | ~8 lines |

Everything else is new files under `doctor_dictation/hx/`, `frontend/hx/`, `tests/hx/`.

## 7. Risks and fallbacks

| Risk | Likelihood | Fallback ready by |
|---|---|---|
| SAM 3.1 not on the Meta API, or too slow per frame | Medium | Day 0: record the demo footage, run SAM (API or Colab GPU) offline, save `detections.jsonl`, replay it |
| Track IDs break when hands pass over the tray | High | `DWELL` + zone logic; manual "+1" button; film with a top-down camera and short occlusions |
| `LLM_PROVIDER=meta` endpoint not OpenAI-compatible | Medium | Day 0 spike S2; fall back to `groq` or `openai` for wording (state it in the submission) |
| Muse STT mishears drug names | Medium | Lexicon `keywords` hints (already sent by `muse.py`); confirm tap; re-take |
| Pre-existing code not allowed | Unknown | Read rules on Day 0. If strict: submit only `hx/` + a thin standalone shell; reuse `core/` as a declared dependency |
| Time overrun | High | Cut order: brown-bag → LLM wording (keep template) → discharge `.ics` → live SAM (keep replay) |

## 8. Submission checklist

- [ ] Video ≤ 3:00, captions on, "synthetic data" and "research demo" stated on screen.
- [ ] README section: how to run (`HACKATHON=1 DECISION_TIER=1 VISION_ADAPTER=replay uvicorn …`).
- [ ] Notes: what was live, what was replayed, measured Count Guard accuracy, which LLM worded the card.
- [ ] Statement of pre-existing code and the `git diff main...hackathon` boundary.
- [ ] No keys, no `.env`, no real images in the repo.
