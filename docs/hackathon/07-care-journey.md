# 07 — Care journey: one patient, three people

**Status:** 28 Oct 2026. Supersedes the demo script in `03-hackathon-spec.md` §3. The backend is built and
tested; the screens are being built. Synthetic data only. Research demo, not for clinical use.

## One-page summary

The demo follows one patient, **R. Kumar, 58 M**, from an outpatient prescription to home after a
day-care hernia repair. Three people each have their own story on **one timeline**:

| Hero | Their story | Where it happens |
|---|---|---|
| **Doctor** | Prescribes, sets ward orders and limits, confirms theatre drugs, signs the discharge card | Doctor Dictation, then `/doctor` |
| **Nurse** | Closes the swab count, logs doses and observations, answers nudges | `/ot`, `/nurse` |
| **Patient** | Scans strips against the prescription, adds dose reminders, reads the discharge card, checks in from home | `/patient` |

**The line we hold.** The system documents and nudges. It never recommends a medicine, dose or procedure.
A nudge is allowed only when it sets a **recorded fact** beside a **recorded intent** that a person wrote:

| Nudge (allowed) | Recommendation (not allowed) |
|---|---|
| "Paracetamol is ordered every 6 h. The last dose was logged 7 h 25 min ago." | "Give paracetamol now." |
| "Systolic BP 86 is below the limit of 90 set by Dr. A. Rao." | "BP is low, consider fluids." |
| "This strip reads amlodipine 10 mg. The prescription says 5 mg." | "Take half a tablet." |

Each nudge stores the ids of the intent event and the fact event it compares, so it can be audited.

## Decisions taken (28 Oct)

| # | Decision | Effect |
|---|---|---|
| J1 | **Option A:** Doctor Dictation stays its own app. Count Guard reads a saved prescription over HTTP (`GET /api/v1/documents/{id}`). | No code is copied between the apps. Verified live: document 1 imported, schedule built. |
| J2 | **Build-now cut** below. Everything else is planned, not built. | Four rules + screens on the existing timeline. No new storage. |
| J3 | **Three-act script** below replaces `03` §3. | The story is filmed as one patient across two days. |
| J4 | **Muse models** for every model call: Voice Transcribe (spoken lines), Spark 1.3 (strip photo, second look), Spark Open (count explanation), SAM 3.1 (count). | One `META_API_KEY` in the root `.env`. Without a key, typed input works and nothing is sent. |

## Build-now cut (status)

| Item | Hero | Status |
|---|---|---|
| Import the prescription from Doctor Dictation (option A), or use the synthetic one | Doctor | Built |
| Ward orders: doses with an interval, observation round, limits | Doctor | Built |
| Strips vs prescription → strength differs / not prescribed nudge | Patient | Built |
| Dose schedule (morning / afternoon / night) and `.ics` reminders | Patient | Built |
| Strip photo read by Muse Spark 1.3 (only with a key) | Patient | Built |
| Dose log (typed or spoken line) vs orders → overdue / logged early / not ordered | Nurse | Built |
| Observations vs the doctor's limits; missed round | Nurse | Built |
| Open count at closing becomes a nurse nudge | Nurse | Built |
| Discharge card from a clinic template (warning signs, wound care, help line) | Doctor → Patient | Built |
| Need help button and home check-in → nurse nudge | Patient → Nurse | Built |
| Nudge inbox with an answer that is logged | Nurse, Patient | Built |
| Shift handover from the timeline; Muse Spark Open rewording kept only if it adds no number, medicine or advice | Nurse → Nurse | Built |
| Audit view: every line, who, when, what replaced it | All | Built |
| Screens `/journey`, `/doctor`, `/nurse`, `/patient`, `/audit` | All | In progress |

**Planned, not built:** SMS/WhatsApp reminders;
voice check-in by phone; wound photo check-in; multi-patient ward board; HL7 vitals feed; signed-in roles.

## Three-act script (≈ 3:00)

`POST /journey/episodes/{id}/play` writes this whole story through the same rules. The times are the
episode clock (`Day 0 09:00` is the OPD visit).

| Time in video | Act | On screen | Rule that fires |
|---|---|---|---|
| 0:00–0:10 | Title | "One patient, three people" | — |
| 0:10–0:35 | **Doctor** | Doctor Dictation: dictate, save. `/doctor`: import document → prescription rows | — |
| 0:35–0:55 | **Patient** (Day 0, 19:00) | `/patient`: scan strips; amlodipine reads 10 mg → nudge; pharmacist swaps it; reminders added | `strip_strength_differs` |
| 0:55–1:25 | **Nurse** (Day 1, theatre) | `/ot`: 20 swabs opened, 19 back → nudge; swab found in drape, count corrected 20/20 | `count_open` |
| 1:25–2:05 | **Nurse** (Day 1, ward) | `/nurse`: BP 86 below Dr. Rao's 90 → nudge, answered. Ondansetron logged twice 30 min apart → nudge. 18:30 check: paracetamol overdue, obs round missed → nurse logs both. 19:00 handover Meena → Kavya, accepted | `obs_past_limit`, `dose_logged_early`, `dose_overdue`, `obs_overdue` |
| 2:05–2:40 | **Patient** (Day 1 → Day 3) | Discharge card signed at 20:00. Day-2 check-in ticks "Fever above 38 °C"; Need help: "The dressing is wet." | `warning_sign_ticked`, `help_requested` |
| 2:40–2:55 | **All** | `/audit`: every line, the two corrections struck through, every nudge and its answer | — |
| 2:55–3:00 | Close | "It documents and nudges. People decide." | — |

## Acceptance checks (automated in `count-guard/backend/tests/test_journey.py`)

- The play completes all three stories (4/4 each) and leaves two open nudges for the nurse.
- No nudge text in the play matches the advice check (`app/agent/verifier.py` `ADVICE`) or an instruction
  verb (give, take, stop, increase, reduce, start, administer, consider).
- A nudge key is raised once; answering it closes it and keeps it in the audit.
- The observation round starts at the first ward set and every due-time check stops at discharge.
- Handover: a rewording that adds a number, a medicine or advice wording is dropped and the template is kept;
  a failed or missing model call keeps the template and says why.
- Option A: a missing document is 404; Doctor Dictation not running is 502 naming the address.

## Appendix: where the code is

| What | File |
|---|---|
| Prescription import (option A) and the synthetic prescription | `count-guard/backend/app/journey/rx.py` |
| Schedule and `.ics` reminders | `count-guard/backend/app/journey/schedule.py` |
| The nudge rules | `count-guard/backend/app/journey/nudges.py` |
| Stories, clinic template, audit rows | `count-guard/backend/app/journey/stories.py` |
| Routes (`/journey/episodes/{id}/...`) | `count-guard/backend/app/journey/api.py` |
| The three-act play | `count-guard/backend/app/journey/play.py` |
| Shift handover: template, Spark Open rewording, wording check | `count-guard/backend/app/journey/handover.py` |
| Strip reading with Muse Spark 1.3 | `count-guard/backend/app/adapters/spark.py` (`read_strips`) |
| Doctor Dictation address | `count-guard/backend/app/config.py` (`dd_base`, from `DD_BASE_URL` or `DD_PORT`) |
