# 05 — Product spec: the patient timeline for real clinics

## 1. Summary

Ship the extension in **risk order**: the documentation tier first (timeline, voice drug log, discharge
draft, brown-bag list), then the safety aid (Count Guard) after a validation study, and the decision tier
(vitals context card, duplicate flag) only after a regulatory opinion and a quality system exist.

| Phase | Delivers | Tier | Engineering time* | Gate to start the next phase |
|---|---|---|---|---|
| P0 | Timeline in `core/`, ports in `providers/`, multi-worker stream, tier switch | — | 3–4 weeks | Isolation suite + hazard log reviewed |
| P1 | Voice drug log, discharge draft, `rx.saved` link | Doc | 5–6 weeks | Pilot with one surgeon, 20 procedures |
| P2 | Brown-bag medicine list (duplicate flag built, switched off) | Doc (+gated) | 4 weeks | Strip-reading accuracy ≥ 95% on 300 strips |
| P3 | Count Guard on a local GPU box | Unclear | 8–12 weeks + validation study | Bench + live study; regulatory opinion |
| P4 | Vitals context card on an HL7 feed | Decision | 12–16 weeks + regulatory | SaMD classification, QMS, clinical evaluation |

\* Two engineers, a part-time clinical lead and a regulatory adviser. Documentation tier (P0–P2) ≈ 3 months.
All five phases ≈ 6–9 months of engineering; regulatory approval for P4 can add 6–12 months on top.

## 2. Users and screens

| User | Place | Screen | Sees |
|---|---|---|---|
| Doctor (existing) | OPD | Rx workspace + brown-bag tab | Prescription, OPD medicine list |
| Surgeon | OT | Push-to-talk button only (foot pedal later) | Nothing new; speaks drug entries |
| Circulating nurse | OT | Count Guard panel (tablet) | IN/OUT counts, closing card, frames |
| Anaesthetist | OT | Vitals context panel (beside the monitor) | Context card, checklist link |
| Ward doctor | Discharge | Discharge draft editor | Folded sections, editable narrative, sign |

The anaesthetist owns the vitals card (README D3). The surgeon gets no screen: their hands are scrubbed.

## 3. Functional requirements

Each requirement has an ID so tests and the hazard log can point at it (`06` §5).

### Timeline (P0)

- **TL-1** Every module writes events through one `TimelineStore.append()`; no module writes SQL directly.
- **TL-2** Events are append-only; corrections use `supersedes_id`; the database refuses `UPDATE` of
  `payload` (trigger) and `DELETE` (trigger).
- **TL-3** Each append writes `audit_log` in the same transaction.
- **TL-4** The stream delivers every event to every worker's clients within 1 s (DB poll on `id`).
- **TL-5** Timeline data is per clinic (each clinic's own SQLite file) and is covered by the isolation suite.
- **TL-6** Decision-tier events are invisible to any API, view, export or PDF while the clinic's tier
  switch is off.

### Voice drug log (P1)

- **DL-1** Push-to-talk; audio is never stored after transcription unless the clinic opts in.
- **DL-2** Drug names ground through the same lexicon, clinic formulary and overlay as Rx.
- **DL-3** An ungrounded or look-alike name needs an explicit confirm, as in the Rx save gate.
- **DL-4** The clinical time `at` defaults to the moment talk was pressed; the user can correct it.

### Discharge draft (P1)

- **DC-1** Sections come from the fold, never from the LLM. The LLM writes only the narrative paragraph
  from the dictated operative note, grounded like `/api/format`.
- **DC-2** The draft is unsigned until a doctor signs it; signing writes `discharge.signed` and a
  `documents` row; the PDF uses the clinic letterhead.
- **DC-3** Follow-up dates export as `.ics`; calendar sync is out of scope.

### Brown-bag list (P2)

- **BB-1** Each listed medicine keeps the photo crop it was read from as evidence.
- **BB-2** Unreadable strips are listed as "unreadable", never guessed.
- **BB-3** Drug classes come from a licensed, versioned source, not a hand map.
- **BB-4** The duplicate flag exists in code and is off unless the decision tier is enabled.

### Count Guard (P3)

- **CG-1** Vision runs on a local GPU box in the OT (SAM 3.1 open weights). No frame leaves the site.
- **CG-2** The screen never shows a green "count OK". It shows "camera count agrees" or "camera count
  differs by N". The manual count remains the record.
- **CG-3** Frames are kept only for the closing card and are deleted after the episode closes, unless the
  clinic opts in for audit.
- **CG-4** Camera loss or low confidence shows "camera count unavailable", never a stale number.

### Vitals context card (P4)

- **VC-1** Readings arrive from the monitor's HL7 v2 feed through the hospital interface engine.
- **VC-2** Rules fire within 200 ms of a reading; the template card shows before any LLM call.
- **VC-3** The LLM runs locally or not at all; the wording check (`02` §5.3) is mandatory.
- **VC-4** The card never contains a drug, dose or action recommendation (tested with a banned-term list
  and a red-team prompt set).
- **VC-5** Data older than 30 s marks the card "stale".

## 4. Non-functional requirements

| Area | Requirement |
|---|---|
| Latency | Rule-to-screen ≤ 1 s (P3, P4); drug-log entry visible ≤ 4 s after release of talk |
| Availability | OT modules keep working with the internet down (local box); sync when back |
| Privacy | India DPDP Act 2023 duties: purpose limitation, consent notice, breach reporting; no identifiers to any cloud model without a DPA |
| Security | Existing auth, sessions, per-clinic scope; OT devices enrolled per clinic; TLS on the LAN |
| Audit | Every append, confirm, sign, tier change and export in `audit_log` |
| Retention | Clinic-configurable; defaults agreed with the clinical lead |
| Scale | ≤ 20 OTs per clinic; ≤ 10 events/s per OT; SQLite per clinic stays sufficient |

## 5. Deployment shape

```
 Clinic LAN                                             Cloud VPS (existing)
 ┌────────────────────────── OT edge box (GPU) ─────┐   ┌──────────────────────────┐
 │ app (same codebase, EDGE=1) · SAM 3.1 local      │◄──┤ OPD app, auth directory, │
 │ local LLM for wording · HL7 listener · SQLite    │──►│ backups (R2), letterhead │
 └──────────────▲───────────────────────────────────┘   └──────────────────────────┘
        tablets, camera, monitor feed
```

The edge box runs the same package with `EDGE=1`. It syncs signed events to the clinic database on the VPS
(append-only makes sync a merge by `(device, id)`). Sync design is part of P3, not P0.

## 6. From hackathon to product: keep or rewrite

| Hackathon piece | Verdict | Why |
|---|---|---|
| Event kinds and payloads (`02` §4.3) | **Keep**, add `payload_v` migrations | It is the contract every module shares |
| `hx/rules/*` pure cores with tests | **Keep**, move into `core/<module>/`, add tests to meet `06` | Already pure and tested |
| `hx/store.py` in-process bus | **Rewrite** | Breaks with 2 workers (TL-4) |
| `hx/api.py` behind `HACKATHON=1` | **Rewrite** as one router per module with auth and scope | Hackathon routes skip auth checks |
| `vision_replay` | **Keep for tests only** | Deterministic fixtures |
| `vision_sam` (cloud) | **Drop** for product | CG-1 forbids frames leaving the site |
| `vitals_sim` | **Keep** for training mode and tests | |
| Hand-made class map | **Drop** | BB-3 |
| Frontend `hx/` pages | **Rewrite** to the design system (tokens in `polish.css`), with `test_frontend_*` tests | Built for the camera, not for daily use |
| Migration `011_timeline.sql` | **Renumber** to the next free number on `main`, add TL-2 triggers | |

## 7. Safety: hazard log seed (ISO 14971 style)

| # | Hazard | Cause | Control | Req |
|---|---|---|---|---|
| H1 | Retained swab | Staff trust a camera "agrees" and skip the manual count | Never show "OK"; manual count stays the record; training | CG-2 |
| H2 | Wrong drug in the record | STT mishears a look-alike name | Lexicon grounding, look-alike guard, confirm tap | DL-2, DL-3 |
| H3 | Wrong cause on the card | Fact attributed to the wrong event | Every fact links to its source event; wording check | VC-3 |
| H4 | Card read as advice | LLM adds an action verb | Banned-term check; template fallback; red-team set | VC-4 |
| H5 | Stale reading shown as current | Feed drops | Staleness marker | VC-5, CG-4 |
| H6 | Decision features on by mistake | Misconfiguration | Default off, admin-only, audited, banner when on | TL-6 |
| H7 | Patient data leaves the site | Cloud model call | Local models for OT; DPA and redaction for OPD cloud calls | CG-1, VC-3 |

## 8. Regulatory workstream (parallel to engineering)

1. Intended-use statement per module (documentation vs decision) — before P3.
2. Regulatory opinion on Count Guard (India CDSCO, plus FDA if exporting) — before P3 pilot.
3. For P4: SaMD classification, a quality management system (ISO 13485), software lifecycle to
   IEC 62304, risk management to ISO 14971, clinical evaluation plan.
4. Until then, decision-tier code ships switched off and labelled "research".

## 9. Open questions

- Which hospital interface engine and monitor models does the first OT partner use? (P4 scope)
- Edge box hardware budget per OT? (P3)
- Licensed drug-class source and its cost? (P2)
- Does the pilot clinic want frames kept for audit? (CG-3 default)
