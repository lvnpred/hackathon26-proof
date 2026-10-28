# Resume point: multi-clinic / multi-doctor build

Last updated 2026-10-14. Spec: `specs/2026-10-14-multi-clinic-multi-doctor-design.md`.

| Plan | File (in `plans/`) | State |
|---|---|---|
| M1 clinic scope + directory | `2026-10-14-m1-clinic-scope-and-directory.md` | Built and reviewed, uncommitted (478 passed, 1 skipped) |
| M2a auth primitives | `2026-10-14-m2a-auth-primitives.md` | BUILT and reviewed, uncommitted (535 passed, 1 skipped; 57 new tests incl. 3 from the final-review fix wave) |
| M2b login over HTTP + UI | `2026-10-14-m2b-login-http-and-ui.md` | BUILT and reviewed, uncommitted (597 passed, 1 skipped). Browser-checked only before the final fix wave; focus rings never checked |
| M2c logout ends only that session | `2026-10-14-m2c-logout-single-session.md` | BUILT, reviewed, uncommitted |
| M3 authorship + profile split | `2026-10-14-m3-authorship-and-profile-split.md` | BUILT, reviewed, uncommitted (655 passed) |
| M4 letterhead scope + OP prefix | `2026-10-14-m4-letterhead-scope-and-op-prefix.md` | BUILT and reviewed, uncommitted (734 passed). Browser-checked for Profile/letterhead items 1-5,7,8 before the fix rounds; PDFs from saved prescriptions and single mode never browser-checked |
| M5 Team screen | `2026-10-14-m5-team-screen.md` | BUILT and reviewed, uncommitted (793 passed). Team UI browser-checked for most flows (not: self/last-user messages, second clinic, single mode, Tab, clipboard fallback, styling) |
| M6 isolation suite + demo | `2026-10-14-m6-isolation-suite-and-demo.md` | BUILT and reviewed, uncommitted (891 passed, 1 skipped). Browser demo run saved under .superpowers/demo-evidence/ (git-ignored); mic/STT/Save UI step used an API fallback |

Next step: all plans (M1-M6, M2c) are built and reviewed. M1-M2b are committed as ae5864c on local `main` (not pushed); M2c, M3, M4, M5, M6 are uncommitted in the working tree. Open items: commit/push decision; rehearse real dictation + real printing by hand; one dry run of `adopt-existing` on a COPY of the real data folder.
Run the suite with `.venv/bin/python -m pytest tests/ -q`.
Open spec s16 items use the plan defaults: 12 h session, 5 fails / 5 min lockout, usernames 3-40 `[A-Za-z0-9._-]`, password 10-200.

## State saved 2026-10-15 (after M6): deployment readiness

Code: M1-M6 and M2c are built, reviewed, committed and pushed (`ae5864c`, `62454c1` on `origin/main`); 891 passed, 1 skipped.

**Ready for:** a controlled demo or pilot on one trusted host (two clinics, per-doctor logins, isolation suite green).
**Not ready for:** a public or real-patient-data deployment. Missing, in order:
1. D0b container and proxy (plan `plans/2026-10-13-d0b-container-and-deploy.md`) was never built: no Dockerfile, no HTTPS proxy, no data volume, no load test, no runbook.
2. D0a hardening (plan `plans/2026-10-13-d0a-auth-and-hardening.md`) was never built: CORS is still `allow_origins=["*"]` (`api/app.py:75`), no security headers or CSP, no demo banner. Its shared basic-auth part is superseded by the session login. NAME CLASH: D0a would reuse the `DEMO_MODE` setting for a banner; `seed-demo` already uses `DEMO_MODE=1`. Rename one before building D0a.
3. Backups and restore (spec: copy the clinic folder after flushing the WAL) have no tooling and no tested restore.
4. Real printing in Chrome/Safari, real dictation through the UI, a real vision model and an iPhone HEIC were never verified; `adopt-existing` never dry-run on a copy of the real data.
5. No voluntary change-password screen (only the forced first-login one), no audit viewer, no log/monitoring setup, `/docs` open to signed-in users, `/health` public.
6. Operational settings to get right: `--proxy-headers --forwarded-allow-ips=<proxy>` (lockout is per username+IP), strong `SESSION_SECRET`, SQLite >= 3.35, `DEMO_MODE` unset, server timezone (OP day rolls at local midnight).
7. Medical-data compliance (consent, retention, breach process) is a business/legal item, not code.

### Resume here (saved 2026-10-15)
Pending decision for the user: build the deployment pieces in this order, or a minimal single-machine pilot only?
Proposed order: (1) D0a hardening: lock CORS to an allow-list, security headers, and rename `DEMO_MODE` (D0a banner) vs `seed-demo`'s `DEMO_MODE=1` first; (2) D0b container + HTTPS proxy + runbook; (3) backup/restore with a tested restore; (4) hand rehearsal of real dictation and real printing, and a dry run of `adopt-existing` on a COPY of the real data folder.
Housekeeping: this file's edits are uncommitted; untracked and never committed: `.agents/ .claude/ .hermes/ skills/ skills-lock.json`; local `master` is stale at `8d699e0`.
Working rules that apply on resume: subagent-driven flow with prompts written to FILES (inline prompts got truncated); agents must never run single mode, `seed-demo` or the demo script against `doctor_dictation/data` (use a temp `DATA_DIR`); no commits or pushes without being asked.
Suite: `.venv/bin/python -m pytest tests/ -q` -> 891 passed, 1 skipped.

### Pending list (saved 2026-10-16, updated after commit f5b66c3)
Everything built is committed and pushed (`origin/main` = f5b66c3; 944 passed, 1 skipped). D0b is DONE and verified with Podman: `Dockerfile`, `docker-compose.yml`, `Caddyfile`, `.env.production.example`, `docs/deploy/runbook.md`, `tests/load/run_load.py` (2400-request gate passed, p95 0.69 s, peak 524 MiB, 800/800 PDFs, 0 zombies; backup/restore round trip OK; 413 limits OK; Secure cookie OK). Not verified: real certificate (needs a public domain), real OpenAI/dictation, a 2 CPU / 2 GB host, Docker itself.
**Housekeeping:** the demo server (8765) and Podman VM are stopped; still to delete when wanted: the demo temp DATA_DIR (path in /tmp/dd_demo_dir; secret in the session scratchpad), the Podman VM (`podman machine rm`) and image `localhost/doctor-dictation:local`; untracked and never committed: `.agents/ .claude/ .hermes/ skills/ skills-lock.json`; local `master` is stale at `8d699e0`.
**Decisions:** shorten the top-bar doctor name when two doctors (e.g. first doctor only)?; add a "designation" field (e.g. CONSULTANT UROLOGIST) and a pad-style phone/timing placement?; what the doctors choice (author/all/selected) should do for AI-read letterheads that no longer contain a doctors block.
**Never verified:** real dictation (mic, speech-to-text, Save) in a browser; real printing in Chrome/Safari; iPhone HEIC photo; `adopt-existing` dry run on a COPY of the real data; forced password change at first sign-in; Team screen self-disable/last-user messages; Safari/Firefox; multi-doctor footer.
**Deployment still open:** D0a hardening (CORS allow-list instead of `*`, security headers/CSP, rename the `DEMO_MODE` clash); backup is a manual runbook step (no scheduler); trim public `/api/health` (shows model names); `/docs` open to signed-in users; `Secure` cookie trusts X-Forwarded-Proto (the app trusts forwarded headers from any peer, safe only while its port is off public interfaces); no voluntary change-password screen; no audit viewer or log monitoring; set SESSION_SECRET strongly, SQLite >= 3.35, DEMO_MODE unset, server timezone (OP day); medical-data compliance (consent, retention, breach process). Next suggested: D0a, then a hand rehearsal of real dictation and printing.
**Known limits/minors:** footers stack doctors (no table); address newlines are flattened; accepting a colleague's clinic draft writes the pad's doctor details into the accepter; draft letterheads have no owner; some writes are two commits (not atomic); test suite ~49 s (seeding with scrypt per test); a few deferred review minors listed in the plans' ledgers (deleted) are summarised in the earlier final reports.

### Medication-name accuracy (saved 2026-10-16)
Proposal saved at `plans/2026-10-16-medication-name-accuracy.md` (NOT approved, no code). Key finding: a mix-up between two drugs that are both in the lexicon (e.g. Prednisone/Prednisolone, ~120 pairs) gets a green "verified" tick because grounding checks the app's own normalized transcript. Proposed order: P1 look-alike guard + indication check + "heard" text, then P2 bigger lexicon / better STT hints / clinic formulary, with a silent-wrong-rate benchmark. Open decisions: approve P1; brand policy (generic, brand or both); collect 50-100 consented dictations.
